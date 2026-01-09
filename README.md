# 🎯 Polymarket Insider Detection Bot

Polymarket'te **insider trading pattern'lerini** tespit eden ve Telegram'a bildirim gönderen bot.

## 🔍 Ne Yapar?

Gerçek insider vakalarından (Maduro, Nobel Prize) öğrenilen pattern'leri kullanarak şüpheli işlemleri tespit eder:

- **Yeni cüzdan** (≤30 gün) + **büyük bahis**
- **Az işlem** (≤10 trade) + **longshot** (≤%20)
- **Yüksek hacim %** (market hacminin ≥%5'i)
- **Yakında biten** market (24 saat içinde)

## 📊 Sinyal Seviyeleri

| Seviye | Koşul | Emoji |
|--------|-------|-------|
| **ACIL** | Yakında bitiyor + başka sinyal | 🚨🚨 |
| **ÇOK GÜVENİLİR** | 3+ sinyal | 🚨 |
| **GÜVENİLİR** | Yeni cüzdan + (az işlem veya longshot) | 🔥 |
| **ORTA** | 2 sinyal (diğer kombinasyonlar) | ⚠️ |

## 📱 Örnek Bildirim

```
🔥 GÜVENİLİR 🔥

Will X announce Y by January 10?

🟢 $15,000 → Yes @ %12.5

━━━━ 🎯 SİNYALLER ━━━━
   🆕 Yeni Cüzdan (3 gün)
   👶 Az İşlem (4 işlem)
   🎰 Longshot Bahis (%12.5)
   📍 Güvenilirlik: GÜVENİLİR

━━━━ 📊 MARKET ━━━━
   Hacim: $250,000
   Likidite: $80,000
   Bu işlem/Hacim: %6.0

━━━━ 👛 CÜZDAN ━━━━
   0x31a5...86e9
   Yaş: 3 gün ⚠️
   İşlem: 4 ⚠️
   PnL: 🟢 $1,200
   ROI: 📈 %15.2
   İlk işlem: 2026-01-06

🔗 Polymarket
```

## 💰 Cashout Takibi

Bot, bildirdiği BUY işlemlerinin SELL'lerini (cashout) de takip eder:

```
💰💰 CASHOUT DETECTED 💰💰

Will X happen?

🔴 $18,000 ← Yes SATIŞ

━━━━ 📊 İŞLEM DETAYI ━━━━
   Alış: $12,000 @ %15.0
   Satış: $18,000 @ %22.5
   🟢 Kar/Zarar: $6,000 (%50.0)

━━━━ 👛 CÜZDAN ━━━━
   0x31a5...86e9
   Toplam PnL: 🟢 $50,000

🔗 Polymarket
```

## 🚀 Kurulum

### 1. Telegram Bot Oluşturma

1. [@BotFather](https://t.me/BotFather)'a gidin
2. `/newbot` yazın
3. Token'ı kaydedin

### 2. Chat ID Alma

**Kişisel:** [@userinfobot](https://t.me/userinfobot)'a `/start` yazın

**Grup için:** Botu gruba ekleyin, `https://api.telegram.org/bot<TOKEN>/getUpdates` adresinden grup ID'sini alın (negatif sayı)

### 3. Çalıştırma

```bash
# Klonla
git clone <repo-url>
cd polymarket-bot

# Virtual environment (opsiyonel)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Dependencies
pip install -r requirements.txt

# Environment variables
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# Çalıştır
python polymarket_whale_bot.py
```

### 4. Systemd Service (Opsiyonel)

```ini
# /etc/systemd/system/polymarket-bot.service
[Unit]
Description=Polymarket Insider Detection Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/polymarket-bot
Environment=TELEGRAM_BOT_TOKEN=your_token
Environment=TELEGRAM_CHAT_ID=your_chat_id
ExecStart=/root/polymarket-bot/venv/bin/python polymarket_whale_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable polymarket-bot
sudo systemctl start polymarket-bot
sudo journalctl -fu polymarket-bot  # Logları izle
```

## ⚙️ Konfigürasyon

`polymarket_whale_bot.py` içinde `Config` class'ını düzenleyin:

```python
@dataclass
class Config:
    min_trade_amount: float = 4000      # Minimum işlem ($)
    max_wallet_age_days: int = 30       # Yeni cüzdan eşiği
    max_trade_count: int = 10           # Az işlem eşiği
    max_probability_longshot: float = 20 # Longshot eşiği (%)
    min_volume_percentage: float = 5    # Hacim % eşiği
    poll_interval: int = 10             # Kontrol sıklığı (saniye)
```

## 🔌 API Endpoints

| Endpoint | Amaç | Sıklık |
|----------|------|--------|
| `data-api.polymarket.com/trades` | $4K+ işlemler | 10sn |
| `gamma-api.polymarket.com/public-profile` | Cüzdan PnL, volume | Her işlem |
| `data-api.polymarket.com/activity` | İşlem sayısı, yaş | Her işlem |
| `gamma-api.polymarket.com/markets` | Market cache | 5dk |
| `gamma-api.polymarket.com/events` | Hacim (fallback) | Gerektiğinde |

## 📚 Araştırma Kaynakları

Bot, gerçek insider vakalarından öğrenilen pattern'leri kullanır:

- **Maduro Vakası**: 3 yeni cüzdan, $630K profit, olay öncesi günlerde oluşturulmuş
- **Nobel Prize**: Tek cüzdan, tek işlem, $50K longshot bahis

## ⚠️ Limitasyonlar

1. **Cluster tespiti yok** - Birbirine bağlı cüzdanları tespit edemez
2. **10sn polling** - Insider pozisyon almış olabilir
3. **False positive** - Her sinyal insider değil
4. **Likidite** - Sinyal görseniz bile giriş yapamayabilirsiniz

## 📄 Lisans

MIT

## ⚠️ Disclaimer

Bu bot sadece bilgilendirme amaçlıdır. Yatırım tavsiyesi değildir. Polymarket'te işlem yapmak risk içerir. Insider trading yasadışıdır.
