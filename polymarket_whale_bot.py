"""
Polymarket Insider Detection Bot v5
Improved wallet age detection, trade counting, and error handling.

INSIDER SIGNALS (must match at least 1):
1. New wallet (<30 days) - uses blockchain age
2. Low trade count (<10 real trades) - filters out splits/merges
3. Low probability (<20%) + High bet ($5K+) - Longshot pattern
4. Disproportionate volume (>5% of market volume)

Research sources:
- Maduro case: 3 new wallets, $630K profit, created days before event
- Nobel Prize: Wallet "6741" - single trade, single market, $50K bet
"""

import asyncio
import aiohttp
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Dict, Set, List
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class Config:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Thresholds
    min_trade_amount: float = 4000
    
    # Insider detection parameters
    max_wallet_age_days: int = 30
    max_trade_count: int = 10
    max_probability_longshot: float = 20
    min_volume_percentage: float = 5
    
    # Polling
    poll_interval: int = 10  # Increased for safety
    error_backoff: int = 30  # Backoff on errors
    
    # APIs
    gamma_api: str = "https://gamma-api.polymarket.com"
    data_api: str = "https://data-api.polymarket.com"
    polygon_rpc: str = "https://polygon-rpc.com"  # Public RPC

config = Config()

class SignalType(Enum):
    NEW_WALLET = "🆕 Yeni Cüzdan"
    LOW_ACTIVITY = "👶 Az İşlem"
    LONGSHOT_BET = "🎰 Longshot Bahis"
    HIGH_VOLUME_PCT = "📊 Yüksek Hacim %"
    ENDING_SOON = "⏰ Yakında Bitiyor"


# =============================================================================
# POLYMARKET CLIENT
# =============================================================================

class PolymarketClient:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.market_cache: Dict[str, Dict] = {}
    
    async def start(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
    
    async def stop(self):
        if self.session:
            await self.session.close()
    
    async def load_markets(self):
        """Load active markets"""
        try:
            url = f"{config.gamma_api}/markets"
            params = {"active": "true", "closed": "false", "limit": 500}
            
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    markets = await resp.json()
                    for m in markets:
                        cond_id = m.get("conditionId", "")
                        if cond_id:
                            self.market_cache[cond_id] = {
                                "question": m.get("question", "Unknown"),
                                "slug": m.get("slug", ""),
                                "volume": float(m.get("volume", 0) or 0),
                                "liquidity": float(m.get("liquidity", 0) or 0),
                            }
                    logger.info(f"📊 Loaded {len(self.market_cache)} markets")
                else:
                    logger.warning(f"Markets API returned {resp.status}")
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
    
    async def get_market_by_slug(self, slug: str) -> Optional[Dict]:
        """Fetch market data by event slug"""
        try:
            # Use events endpoint with slug parameter
            url = f"{config.gamma_api}/events"
            params = {"slug": slug, "closed": "false"}
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        event = data[0]
                        return {
                            "question": event.get("title", "Unknown"),
                            "slug": event.get("slug", slug),
                            "volume": float(event.get("volume", 0) or 0),
                            "liquidity": float(event.get("liquidity", 0) or 0),
                        }
        except Exception as e:
            logger.debug(f"Error fetching event by slug: {e}")
        return None
    
    async def get_large_trades(self, min_amount: float, limit: int = 30) -> List[Dict]:
        """Fetch recent large trades with retry"""
        for attempt in range(3):
            try:
                url = f"{config.data_api}/trades"
                params = {
                    "limit": limit,
                    "filterType": "CASH",
                    "filterAmount": int(min_amount)
                }
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.warning(f"Trades API returned {resp.status}")
            except Exception as e:
                logger.error(f"Error fetching trades (attempt {attempt+1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
        return []
    
    async def get_wallet_info(self, address: str) -> Dict:
        """Get comprehensive wallet info with improved accuracy"""
        info = {
            "address": address,
            "age_days": None,
            "chain_age_days": None,  # Blockchain age
            "trade_count": None,
            "pnl": None,
            "volume": None,
            "first_trade_date": None
        }
        
        if not address:
            return info
        
        # 1. Get Polymarket profile (only working endpoint)
        try:
            url = f"{config.gamma_api}/public-profile?wallet={address}"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get("createdAt"):
                        try:
                            created = datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
                            info["age_days"] = (datetime.now(timezone.utc) - created).days
                        except:
                            pass
                    
                    if data.get("pnl") is not None:
                        try:
                            info["pnl"] = float(data["pnl"])
                        except:
                            pass
                    
                    if data.get("volume") is not None:
                        try:
                            info["volume"] = float(data["volume"])
                        except:
                            pass
        except:
            pass
        
        # 2. Get REAL trade count (only type=="TRADE", not splits/merges)
        try:
            url = f"{config.data_api}/activity"
            params = {"user": address, "type": "TRADE", "limit": 500}
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=5), params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        info["trade_count"] = len(data)
                        
                        # Get first trade date from activity
                        if data:
                            try:
                                # Sort by timestamp to get first
                                sorted_data = sorted(data, key=lambda x: x.get("timestamp", 0))
                                if sorted_data:
                                    first_ts = sorted_data[0].get("timestamp")
                                    if first_ts:
                                        first_date = datetime.fromtimestamp(first_ts, tz=timezone.utc)
                                        info["first_trade_date"] = first_date.strftime("%Y-%m-%d")
                                        # Calculate age from first trade
                                        trade_age = (datetime.now(timezone.utc) - first_date).days
                                        # Use the smaller of profile age or trade age
                                        if info["age_days"] is None or trade_age < info["age_days"]:
                                            info["chain_age_days"] = trade_age
                            except:
                                pass
        except:
            pass
        
        # 3. Try to get blockchain wallet age (first tx ever)
        try:
            # Use Polygon RPC to get transaction count
            # If 0, wallet is brand new
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getTransactionCount",
                "params": [address, "latest"],
                "id": 1
            }
            async with self.session.post(
                config.polygon_rpc,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tx_count = int(data.get("result", "0x0"), 16)
                    if tx_count == 0:
                        # Brand new wallet!
                        info["chain_age_days"] = 0
                        logger.debug(f"Brand new wallet detected: {address}")
        except:
            pass
        
        # Use chain_age if available and smaller
        if info["chain_age_days"] is not None:
            if info["age_days"] is None or info["chain_age_days"] < info["age_days"]:
                info["age_days"] = info["chain_age_days"]
        
        return info

# =============================================================================
# INSIDER DETECTOR
# =============================================================================

class InsiderDetector:
    """Analyzes trades for insider patterns"""
        
    @staticmethod
    def analyze(trade: Dict, wallet: Dict, market: Dict) -> List[SignalType]:
        """Returns list of triggered signals"""
        signals = []
        
        # SKIP: SELL trades - only show BUY
        if trade.get("side", "").upper() == "SELL":
            return []
                
        size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        amount = size * price
        probability = price * 100
        
        market_volume = market.get("volume", 0)
        age_days = wallet.get("age_days")
        trade_count = wallet.get("trade_count")
        
        # SKIP: High probability = obvious bet, not insider
        if probability >= 80:
            return []
        
        # Signal 1: New wallet
        if age_days is not None and age_days <= config.max_wallet_age_days:
            signals.append(SignalType.NEW_WALLET)
        
        # Signal 2: Low activity (real trades only)
        if trade_count is not None and trade_count <= config.max_trade_count:
            signals.append(SignalType.LOW_ACTIVITY)
        
        # Signal 3: Longshot bet
        if probability <= config.max_probability_longshot:
            signals.append(SignalType.LONGSHOT_BET)
        
        # Signal 4: High volume percentage
        if market_volume > 0:
            vol_pct = (amount / market_volume) * 100
            if vol_pct >= config.min_volume_percentage:
                signals.append(SignalType.HIGH_VOLUME_PCT)
        
        # Signal 5: Ending soon (within 24 hours) - STRONGEST insider signal
        end_date = trade.get("endDate") or market.get("endDate")
        if end_date:
            try:
                if isinstance(end_date, str):
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                else:
                    end_dt = datetime.fromtimestamp(end_date, tz=timezone.utc)
                
                hours_until_end = (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                if 0 < hours_until_end <= 24:
                    signals.append(SignalType.ENDING_SOON)
            except:
                pass
        
        return signals
    
    @staticmethod
    def should_alert(signals: List[SignalType]) -> bool:
        """Only alert on strong patterns"""
        # ENDING_SOON is always important - alert if combined with anything
        if SignalType.ENDING_SOON in signals and len(signals) >= 2:
            return True
        
        # 3+ signals = definitely alert
        if len(signals) >= 3:
            return True
        
        # 2 signals = only if strong combo
        if len(signals) == 2:
            has_new = SignalType.NEW_WALLET in signals
            has_low = SignalType.LOW_ACTIVITY in signals
            has_long = SignalType.LONGSHOT_BET in signals
            # Classic insider patterns
            return has_new and (has_low or has_long)
        
        # 1 or 0 signals = skip
        return False
    
    @staticmethod
    def get_priority(signals: List[SignalType], amount: float) -> int:
        """Calculate priority score"""
        priority = 0
        
        # Base by amount
        if amount >= 50000:
            priority += 50
        elif amount >= 20000:
            priority += 30
        elif amount >= 10000:
            priority += 20
        else:
            priority += 10
        
        # Bonus for multiple signals
        priority += len(signals) * 15
        
        # Special combos
        if SignalType.NEW_WALLET in signals and SignalType.LOW_ACTIVITY in signals:
            priority += 25  # Classic insider
        
        if SignalType.LONGSHOT_BET in signals and SignalType.NEW_WALLET in signals:
            priority += 20  # High conviction insider
        
        # ENDING_SOON is very strong signal
        if SignalType.ENDING_SOON in signals:
            priority += 30
        
        return priority

# =============================================================================
# TELEGRAM
# =============================================================================

class TelegramBot:
    def __init__(self):
        self.api = f"https://api.telegram.org/bot{config.telegram_bot_token}"
    
    async def send(self, text: str) -> bool:
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api}/sendMessage",
                        json={
                            "chat_id": config.telegram_chat_id,
                            "text": text,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True
                        }
                    ) as resp:
                        if resp.status == 200:
                            return True
                        err = await resp.text()
                        logger.error(f"Telegram error: {err}")
            except Exception as e:
                logger.error(f"Telegram error (attempt {attempt+1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
        return False
    
    def format_alert(self, trade: Dict, wallet: Dict, market: Dict, signals: List[SignalType], priority: int) -> str:
        size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        amount = size * price
        probability = price * 100
        
        # Header based on signal reliability
        signal_count = len(signals)
        has_new_wallet = SignalType.NEW_WALLET in signals
        has_low_activity = SignalType.LOW_ACTIVITY in signals
        has_longshot = SignalType.LONGSHOT_BET in signals
        has_ending_soon = SignalType.ENDING_SOON in signals
        
        # ENDING_SOON with any other signal = highest priority
        if has_ending_soon and signal_count >= 2:
            header = "🚨🚨 <b>ACIL - YAKINDA BİTİYOR</b> 🚨🚨"
            reliability = "ACIL"
        elif signal_count >= 3:
            header = "🚨 <b>ÇOK GÜVENİLİR</b> 🚨"
            reliability = "ÇOK GÜVENİLİR"
        elif signal_count == 2 and has_new_wallet and (has_low_activity or has_longshot):
            header = "🔥 <b>GÜVENİLİR</b> 🔥"
            reliability = "GÜVENİLİR"
        elif signal_count == 2:
            header = "⚠️ <b>ORTA</b> ⚠️"
            reliability = "ORTA"
        else:
            header = "📊 <b>DÜŞÜK</b> 📊"
            reliability = "DÜŞÜK"
        
        side = trade.get("side", "BUY")
        outcome = trade.get("outcome", "Yes")
        
        if side == "BUY":
            side_emoji = "🟢"
            action = f"→ <b>{outcome}</b>"
        else:
            side_emoji = "🔴"
            action = f"← <b>{outcome} SATIŞ</b> (Cashout)"
        
        # Market
        title = trade.get("title", market.get("question", "Unknown"))
        # Use eventSlug for correct URL (slug is market-specific, eventSlug is event page)
        slug = trade.get("eventSlug") or trade.get("slug") or market.get("slug", "")
        volume = market.get("volume", 0)
        liquidity = market.get("liquidity", 0)
        vol_pct = (amount / volume * 100) if volume > 0 else 0
        
        # Wallet
        addr = wallet.get("address", "Unknown")
        short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        age = wallet.get("age_days")
        trades = wallet.get("trade_count")
        pnl = wallet.get("pnl")
        
        lines = [
            header,
            "",
            f"<b>{title[:80]}</b>",
            "",
            f"{side_emoji} <b>${amount:,.0f}</b> → <b>{outcome}</b> @ %{probability:.1f}",
        ]
        
        # Signals
        lines.append("")
        lines.append("━━━━ <b>🎯 SİNYALLER</b> ━━━━")
        for sig in signals:
            if sig == SignalType.NEW_WALLET:
                lines.append(f"   {sig.value} ({age} gün)")
            elif sig == SignalType.LOW_ACTIVITY:
                lines.append(f"   {sig.value} ({trades} işlem)")
            elif sig == SignalType.LONGSHOT_BET:
                lines.append(f"   {sig.value} (%{probability:.1f})")
            elif sig == SignalType.HIGH_VOLUME_PCT:
                lines.append(f"   {sig.value} (%{vol_pct:.1f})")
            elif sig == SignalType.ENDING_SOON:
                lines.append(f"   {sig.value} (24 saat içinde!)")
        
        # Priority/Reliability
        lines.append(f"   📍 Güvenilirlik: <b>{reliability}</b>")
        
        # Market
        lines.append("")
        lines.append("━━━━ <b>📊 MARKET</b> ━━━━")
        lines.append(f"   Hacim: ${volume:,.0f}")
        lines.append(f"   Likidite: ${liquidity:,.0f}")
        if vol_pct > 0:
            lines.append(f"   Bu işlem/Hacim: %{vol_pct:.1f}")
        
        # Wallet
        lines.append("")
        lines.append("━━━━ <b>👛 CÜZDAN</b> ━━━━")
        lines.append(f"   <code>{short_addr}</code>")
        
        if age is not None:
            age_warning = " ⚠️" if age <= 30 else ""
            lines.append(f"   Yaş: {age} gün{age_warning}")
        
        if trades is not None:
            trade_warning = " ⚠️" if trades <= 10 else ""
            lines.append(f"   İşlem: {trades}{trade_warning}")
        
        if pnl is not None:
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"   PnL: {pnl_emoji} ${pnl:,.0f}")
            
            # Calculate ROI if volume exists
            vol = wallet.get("volume")
            if vol and vol > 0:
                roi = (pnl / vol) * 100
                roi_emoji = "📈" if roi >= 0 else "📉"
                lines.append(f"   ROI: {roi_emoji} %{roi:.1f}")
        
        if wallet.get("first_trade_date"):
            lines.append(f"   İlk işlem: {wallet['first_trade_date']}")
        
        # Link
        if slug:
            lines.append("")
            lines.append(f"🔗 <a href='https://polymarket.com/event/{slug}'>Polymarket</a>")
        
        return "\n".join(lines)
    
    def format_sell_alert(self, trade: Dict, wallet: Dict, market: Dict, original_buy: Dict, profit: float) -> str:
        """Format SELL (cashout) alert"""
        size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        sell_amount = size * price
        
        buy_amount = original_buy.get("amount", 0)
        buy_price = original_buy.get("price", 0)
        outcome = original_buy.get("outcome", "")
        
        # Profit calculation
        profit_pct = ((price - buy_price) / buy_price * 100) if buy_price > 0 else 0
        profit_emoji = "🟢" if profit >= 0 else "🔴"
        
        title = trade.get("title", market.get("question", "Unknown"))
        slug = trade.get("eventSlug") or trade.get("slug") or market.get("slug", "")
        
        addr = wallet.get("address", "Unknown")
        short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        
        lines = [
            "💰💰 <b>CASHOUT DETECTED</b> 💰💰",
            "",
            f"<b>{title[:80]}</b>",
            "",
            f"🔴 <b>${sell_amount:,.0f}</b> ← <b>{outcome} SATIŞ</b>",
            "",
            "━━━━ <b>📊 İŞLEM DETAYI</b> ━━━━",
            f"   Alış: ${buy_amount:,.0f} @ %{buy_price*100:.1f}",
            f"   Satış: ${sell_amount:,.0f} @ %{price*100:.1f}",
            f"   {profit_emoji} Kar/Zarar: ${profit:,.0f} (%{profit_pct:.1f})",
            "",
            "━━━━ <b>👛 CÜZDAN</b> ━━━━",
            f"   <code>{short_addr}</code>",
        ]
        
        if wallet.get("pnl") is not None:
            pnl = wallet.get("pnl")
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"   Toplam PnL: {pnl_emoji} ${pnl:,.0f}")
        
        if slug:
            lines.append("")
            lines.append(f"🔗 <a href='https://polymarket.com/event/{slug}'>Polymarket</a>")
        
        return "\n".join(lines)

# =============================================================================
# MONITOR
# =============================================================================

class InsiderMonitor:
    def __init__(self):
        self.client = PolymarketClient()
        self.telegram = TelegramBot()
        self.detector = InsiderDetector()
        self.seen_trades: Set[str] = set()
        self.alerted_buys: Dict[str, Dict] = {}  # wallet+asset -> trade info (for tracking SELLs)
        self.running = False
        self.consecutive_errors = 0
    
    async def run(self):
        self.running = True
        
        logger.info("🚀 Polymarket Insider Detection Bot v5")
        logger.info(f"   Min amount: ${config.min_trade_amount:,}")
        logger.info(f"   Max wallet age: {config.max_wallet_age_days} days")
        logger.info(f"   Max trade count: {config.max_trade_count}")
        logger.info(f"   Longshot: {config.max_probability_longshot}%")
        logger.info(f"   Volume %: {config.min_volume_percentage}%")
        logger.info(f"   Poll interval: {config.poll_interval}s")
        
        await self.client.start()
        await self.client.load_markets()
        
        # Skip existing
        existing = await self.client.get_large_trades(config.min_trade_amount, limit=50)
        for t in existing:
            tx = t.get("transactionHash", "")
            if tx:
                self.seen_trades.add(tx)
        logger.info(f"📝 Skipping {len(self.seen_trades)} existing trades")
        
        # Startup
        await self.telegram.send(
            "🟢 <b>Insider Detection Bot v5 Started!</b>\n\n"
            f"💰 Min: ${config.min_trade_amount:,.0f}\n"
            f"📅 Max cüzdan yaşı: {config.max_wallet_age_days} gün\n"
            f"📊 Max işlem: {config.max_trade_count}\n"
            f"🎰 Longshot: %{config.max_probability_longshot} altı\n"
            f"📈 Min hacim %: {config.min_volume_percentage}\n\n"
            "Insider pattern arıyorum..."
        )
        
        # Tasks
        poll_task = asyncio.create_task(self._poll_loop())
        refresh_task = asyncio.create_task(self._refresh_loop())
        
        try:
            await asyncio.gather(poll_task, refresh_task)
        except asyncio.CancelledError:
            pass
        finally:
            await self.client.stop()
    
    async def _poll_loop(self):
        """Main polling loop with error handling"""
        while self.running:
            try:
                trades = await self.client.get_large_trades(config.min_trade_amount, limit=30)
                
                if not trades:
                    self.consecutive_errors += 1
                    if self.consecutive_errors >= 3:
                        logger.warning(f"No trades returned, backing off...")
                        await asyncio.sleep(config.error_backoff)
                        self.consecutive_errors = 0
                    continue
                
                self.consecutive_errors = 0
                
                for trade in trades:
                    tx = trade.get("transactionHash", "")
                    if not tx or tx in self.seen_trades:
                        continue
                    
                    self.seen_trades.add(tx)
                    
                    # Get info
                    wallet_addr = trade.get("proxyWallet", "")
                    wallet = await self.client.get_wallet_info(wallet_addr)
                    
                    # Get market info - try cache first, then fetch by eventSlug
                    cond_id = trade.get("conditionId", "")
                    market = self.client.market_cache.get(cond_id)
                    
                    if not market or market.get("volume", 0) == 0:
                        # Try to get from eventSlug (correct slug for event page)
                        event_slug = trade.get("eventSlug") or trade.get("slug", "")
                        if event_slug:
                            market = await self.client.get_market_by_slug(event_slug)
                    
                    if not market:
                        market = {
                            "question": trade.get("title", "Unknown"),
                            "slug": trade.get("eventSlug") or trade.get("slug", ""),
                            "volume": 0,
                            "liquidity": 0
                        }
                    
                    # Analyze
                    signals = self.detector.analyze(trade, wallet, market)
                    
                    size = float(trade.get("size", 0))
                    price = float(trade.get("price", 0))
                    amount = size * price
                    side = trade.get("side", "BUY")
                    asset = trade.get("asset", "")
                    
                    # SELL handling: only alert if we previously alerted a BUY for same wallet+asset
                    if side == "SELL":
                        buy_key = f"{wallet_addr}:{asset}"
                        if buy_key in self.alerted_buys:
                            # This is a cashout of a previously alerted BUY!
                            original_buy = self.alerted_buys[buy_key]
                            logger.info(f"💰 CASHOUT detected: ${amount:,.0f} (original BUY: ${original_buy['amount']:,.0f})")
                            
                            # Calculate profit/loss
                            buy_price = original_buy.get("price", 0)
                            sell_price = price
                            profit = (sell_price - buy_price) * size
                            
                            msg = self.telegram.format_sell_alert(trade, wallet, market, original_buy, profit)
                            if await self.telegram.send(msg):
                                logger.info("✅ Cashout alert sent")
                            
                            # Remove from tracking
                            del self.alerted_buys[buy_key]
                        # Skip other SELLs
                        continue
                    
                    # BUY handling: normal signal check
                    if self.detector.should_alert(signals):
                        priority = self.detector.get_priority(signals, amount)
                        
                        logger.info(f"🎯 INSIDER: ${amount:,.0f} | {[s.name for s in signals]} | P:{priority}")
                        
                        msg = self.telegram.format_alert(trade, wallet, market, signals, priority)
                        if await self.telegram.send(msg):
                            logger.info("✅ Alert sent")
                            
                            # Track this BUY for potential SELL later
                            buy_key = f"{wallet_addr}:{asset}"
                            self.alerted_buys[buy_key] = {
                                "amount": amount,
                                "price": price,
                                "title": trade.get("title", ""),
                                "outcome": trade.get("outcome", ""),
                                "timestamp": trade.get("timestamp", 0)
                            }
                        
                        await asyncio.sleep(0.5)
                    else:
                        logger.debug(f"⏭️ Skip: ${amount:,.0f} | age={wallet.get('age_days')} trades={wallet.get('trade_count')} prob={price*100:.0f}%")
                
                # Trim
                if len(self.seen_trades) > 5000:
                    self.seen_trades = set(list(self.seen_trades)[-2500:])
                
                # Trim old alerted_buys (older than 7 days)
                if len(self.alerted_buys) > 1000:
                    cutoff = datetime.now(timezone.utc).timestamp() - (7 * 24 * 3600)
                    self.alerted_buys = {
                        k: v for k, v in self.alerted_buys.items() 
                        if v.get("timestamp", 0) > cutoff
                    }
                
            except Exception as e:
                logger.error(f"Poll error: {e}")
                self.consecutive_errors += 1
                if self.consecutive_errors >= 3:
                    await asyncio.sleep(config.error_backoff)
            
            await asyncio.sleep(config.poll_interval)
    
    async def _refresh_loop(self):
        """Refresh markets"""
        while self.running:
            await asyncio.sleep(300)
            logger.info("🔄 Refreshing markets...")
            await self.client.load_markets()
    
    def stop(self):
        self.running = False

# =============================================================================
# MAIN
# =============================================================================

async def main():
    if not config.telegram_bot_token or not config.telegram_chat_id:
        logger.error("❌ Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID!")
        return
    
    monitor = InsiderMonitor()
    try:
        await monitor.run()
    except KeyboardInterrupt:
        monitor.stop()

if __name__ == "__main__":
    asyncio.run(main())
