# ⛏️ Skyblock Buffet - Economy & Market Analyzer

Minecraft Hypixel Skyblock sunucusunun karmaşık pazar ekonomisini (Bazaar, Crafting ve Auction House) anlık API verileriyle analiz eden, kar marjlarını ve saatlik tahmini karı (Profit Per Hour - PPH) hesaplayan yeni nesil analiz aracı.

## 🚀 Özellikler (Features)
- 📊 **Bazaar Flipping Motoru**: Gerçek zamanlı Buy Order vs Sell Offer marjları, vergi düşülmüş net kar hesabı.
- 🔨 **Craft Flipping Motoru**: Tüm 3x3 ve shapeless craft tariflerini ayrıştırarak hammadde maliyeti vs satış karı analizi.
- 🏛️ **Auction House (AH / LBIN)**: En ucuz BIN (Lowest BIN) tespiti ve sniping fırsatları.
- ⚡ **Asenkron Mimari**: FastAPI + SQLAlchemy 2.0 (Async) + PostgreSQL + httpx.
- 👥 **Çoklu Kullanıcı Desteği**: İlerleyen süreçte üyelik ve yetkilendirme altyapısı.

## 📁 Proje Yapısı
```text
skyblockbuffet/
├── backend/
│   ├── app/
│   │   ├── core/         # DB bağlantısı, config (.env)
│   │   ├── models/       # PostgreSQL tabloları
│   │   ├── schemas/      # Pydantic veri modelleri
│   │   ├── services/     # Hypixel API, Kar motorları
│   │   └── api/          # REST API endpointleri
│   └── requirements.txt
└── frontend/             # Web Dashboard (Yakında)
```

## 🛠️ Kurulum
```bash
# 1. Depoyu klonlayın
git clone https://github.com/littleketto/skyblockbuffet.git
cd skyblockbuffet

# 2. Sanal ortamı oluşturun ve paketleri yükleyin
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt

# 3. .env dosyasını yapılandırın
cp .env.example .env
```
