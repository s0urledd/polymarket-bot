# 🐋 Polymarket Whale Alert Bot

Polymarket'te büyük işlemleri **real-time** takip eden ve Telegram'a bildirim gönderen bot.

## 🏗️ Hybrid Mimari

```
┌─────────────────────────────────────────────────────────┐
│                    WebSocket                            │
│         wss://ws-subscriptions-clob.polymarket.com      │
│                                                         │
│   last_trade_price events → Anlık tespit ($5K+ check)   │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   Data API                              │
│            data-api.polymarket.com/trades               │
│                                                         │
│   Detay çekme: cüzdan adresi, market bilgisi, PnL       │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  Telegram Bot                           │
│              Formatted alert gönderimi                  │
└─────────────────────────────────────────────────────────┘
```

**Neden Hybrid?**
- **WebSocket**: Anlık tespit (< 1 saniye gecikme)
- **Data API**: Cüzdan adresi, market detayları, kullanıcı bilgileri
- İkisi birlikte = Hızlı + Detaylı

## Özellikler

- **$5K+ işlemleri** takip eder
- **Üç seviye alert**:
  - 🐟 $5K-10K (Fish)
  - 🐬 $10K-20K (Dolphin)  
  - 🐋 $20K+ (Whale)
- **Cüzdan bilgileri**: yaş, işlem sayısı, PnL
- **Market bilgileri**: hacim, likidite, oran
- **Dikkat çekici işaretler**: yeni cüzdan, ilk işlem, düşük olasılık + yüksek bahis

## Örnek Bildirim

```
🐋 POLYMARKET ALERT 🐋

Market: Will X happen by 2025?

🟢 $25,000 → Yes @ %12

━━━━━━━━━━━━━━━━━━━━━━
📊 Market Bilgileri:
   • Toplam hacim: $150,000
   • Likidite: $45,000
   • Bu işlem/hacim: %16.7

👛 Cüzdan Bilgileri:
   • Adres: 0x31a5...b2c4
   • Yaş: 3 gün
   • Toplam işlem: 2
   • PnL: 📈 $1,200

⚠️ Dikkat Çekici:
   • İlk/erken işlem
   • Yeni cüzdan (3 gün)
   • Düşük olasılık + yüksek bahis

━━━━━━━━━━━━━━━━━━━━━━
🔗 Polymarket'te Gör
```

## Kurulum

### 1. Telegram Bot Oluşturma

1. Telegram'da [@BotFather](https://t.me/BotFather)'a gidin
2. `/newbot` yazın
3. Bot adı ve username girin
4. Size verilen **token**'ı kaydedin

### 2. Chat ID Alma

1. [@userinfobot](https://t.me/userinfobot)'a gidin
2. `/start` yazın
3. Size verilen **ID**'yi kaydedin

**Grup için:**
- Botu gruba ekleyin
- Grupta bir mesaj yazın
- `https://api.telegram.org/bot<TOKEN>/getUpdates` adresinden grup ID'sini alın (negatif sayı)

### 3. Botu Çalıştırma

```bash
# Klonla
git clone <repo-url>
cd polymarket-bot

# Dependencies yükle
pip install -r requirements.txt

# Environment variables ayarla
export TELEGRAM_BOT_TOKEN="your_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"

# Çalıştır
python polymarket_whale_bot.py
```

### 4. (Opsiyonel) Docker ile Çalıştırma

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY polymarket_whale_bot.py .
CMD ["python", "polymarket_whale_bot.py"]
```

```bash
docker build -t polymarket-bot .
docker run -d \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e TELEGRAM_CHAT_ID="your_chat_id" \
  polymarket-bot
```

### 5. (Opsiyonel) Systemd Service

```ini
# /etc/systemd/system/polymarket-bot.service
[Unit]
Description=Polymarket Whale Alert Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/polymarket-bot
Environment=TELEGRAM_BOT_TOKEN=your_token
Environment=TELEGRAM_CHAT_ID=your_chat_id
ExecStart=/usr/bin/python3 polymarket_whale_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable polymarket-bot
sudo systemctl start polymarket-bot
```

## Konfigürasyon

`polymarket_whale_bot.py` içinde `Config` class'ını düzenleyebilirsiniz:

```python
@dataclass
class Config:
    # Minimum alert miktarı ($)
    min_trade_amount: float = 5000
    
    # Kaç saniyede bir kontrol
    poll_interval: int = 30
```

## Alert Seviyeleri

| Seviye | Miktar | Emoji |
|--------|--------|-------|
| Fish | $5K - $10K | 🐟 |
| Dolphin | $10K - $20K | 🐬 |
| Whale | $20K+ | 🐋 |

## API Notları

### WebSocket (Real-time) 🔴
```
wss://ws-subscriptions-clob.polymarket.com/ws/market
```
- `last_trade_price` event'leri dinleniyor
- Tüm aktif market'lerin asset_id'lerine subscribe
- Her 5 dakikada market listesi güncelleniyor

### Data API (Detaylar) 📊
```
https://data-api.polymarket.com/trades
```
- Cüzdan adresi (proxyWallet)
- Market bilgileri (title, slug)
- `filterType=CASH&filterAmount=5000` ile filtreleme

### Gamma API (Market Cache) 📈
```
https://gamma-api.polymarket.com/markets
```
- Aktif market listesi
- Asset ID → Market eşleştirmesi
- Volume, liquidity bilgileri

## Bilinen Limitasyonlar

1. **WebSocket desteği yok**: Şu an polling yapıyor. Daha hızlı bildirim için WebSocket eklenebilir.
2. **Cüzdan yaşı**: Her zaman alınamayabiliyor, API'ye bağlı.
3. **Trade geçmişi**: Bazı cüzdanlar için eksik olabilir.

## Geliştirme Fikirleri

- [ ] WebSocket ile real-time tracking
- [ ] Whale wallet watchlist
- [ ] Copy-trade özelliği
- [ ] Web dashboard
- [ ] Historical analiz

## Sorun Giderme

**Bot çalışıyor ama bildirim gelmiyor:**
1. Token ve chat ID'yi kontrol edin
2. Botu Telegram'da `/start` ile başlatın
3. Grup için bot'un mesaj atma yetkisi olduğundan emin olun

**Rate limit hatası:**
- `poll_interval`'ı artırın (örn: 60 saniye)

**Market bulunamadı hatası:**
- Normal, bazı tokenlar için market bilgisi alınamayabilir
- Bot yine de işlemi bildirecek

## Lisans

MIT

## Disclaimer

Bu bot sadece bilgilendirme amaçlıdır. Yatırım tavsiyesi değildir. Polymarket'te işlem yapmak risk içerir.
