import math
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.item import Item
from app.models.bazaar import BazaarSnapshot
from app.schemas.bazaar import BazaarFlipItem


async def calculate_bazaar_flips(
    db: AsyncSession,
    min_profit: float = 0.0,
    min_hourly_volume: int = 0,
    max_budget: Optional[float] = None,
    tax_rate: Optional[float] = None,
    market_share_alpha: float = 0.10,
    limit: Optional[int] = None,
) -> List[BazaarFlipItem]:
    """
    Bazaar Flipping Firsatlarini Hesaplar:
    1. Her urunun alis teklifi (Buy Order) ve satis teklifi (Sell Offer) arasindaki marji bulur.
    2. %1.125 Skyblock pazar vergisini duser.
    3. Haftalik alis ve satis hacimlerinin minimumunu alarak (cunku esyayi hem alip hem satabilmek gerekir)
       gercekci bir saatlik hacim (Hourly Volume) cikarir.
    4. PPH (Profit Per Hour - Saatlik Kar) ve Dengeli Siralama Puani (Ranking Score) hesaplar.
    """
    tax = tax_rate if tax_rate is not None else settings.BAZAAR_TAX_RATE

    # Bazaar snapshotlari ve Item bilgilerini birlestirerek cek
    query = select(BazaarSnapshot, Item).join(Item, Item.id == BazaarSnapshot.item_id)
    result = await db.execute(query)
    rows = result.all()

    flips: List[BazaarFlipItem] = []

    for snapshot, item in rows:
        # Flipping Mantigi:
        # 1. Alis Emri acariz -> Maliyetimiz = snapshot.sell_price (Oyuncularin aninda sattigi fiyat)
        # 2. Satis Emri acariz -> Gelirimiz = snapshot.buy_price (Oyuncularin aninda aldigi fiyat)
        buy_price = float(snapshot.sell_price)
        sell_price = float(snapshot.buy_price)

        # Fiyatlar sifir veya satis fiyati alis fiyatindan kucukse flip yapilamaz
        if buy_price <= 0.1 or sell_price <= 0.1 or sell_price <= buy_price:
            continue

        # Butce filtresi (Kullanicinin belirledigi maksimum coin miktari)
        if max_budget is not None and buy_price > max_budget:
            continue

        # Vergi ve Net Kar Hesabi
        # Net Gelir = Satis Fiyati * (1 - Vergi)
        net_revenue = sell_price * (1.0 - tax)
        profit_per_item = net_revenue - buy_price

        if profit_per_item < min_profit:
            continue

        # Yatirim Getirisi (ROI %)
        margin_percent = (profit_per_item / buy_price) * 100.0

        # Likidite / Hacim Analizi
        # 1 haftada 168 saat vardir.
        # Bir esyayi hem alip hem satabilmemiz icin Alis ve Satis hacminin dengeli olmasi gerekir.
        effective_weekly_volume = min(int(snapshot.buy_moving_week), int(snapshot.sell_moving_week))
        hourly_volume = int(effective_weekly_volume / 168)

        if hourly_volume < min_hourly_volume:
            continue

        # Pazar Payi (Alpha): Bir oyuncu o pazardaki saatlik hacmin yaklasik %10'unu cevirebilir
        fillable_per_hour = max(1.0, float(hourly_volume) * market_share_alpha)
        profit_per_hour = profit_per_item * fillable_per_hour

        # Dengeli Siralama Puani (Ranking Score)
        # Sadece kara bakarsak hacmi 2 olan urunler basa cikar.
        # Sadece hacme bakarsak 1 coin kazandiran urunler basa cikar.
        # Logaritmik hacim carpanli dengeli skor:
        score = profit_per_hour * math.log10(max(10, hourly_volume))

        flips.append(
            BazaarFlipItem(
                item_id=item.id,
                name=item.name,
                tier=item.tier,
                category=item.category,
                buy_price=round(buy_price, 2),
                sell_price=round(sell_price, 2),
                profit_per_item=round(profit_per_item, 2),
                margin_percent=round(margin_percent, 2),
                weekly_buy_volume=int(snapshot.buy_moving_week),
                weekly_sell_volume=int(snapshot.sell_moving_week),
                hourly_volume=hourly_volume,
                profit_per_hour=round(profit_per_hour, 2),
                ranking_score=round(score, 2),
            )
        )

    # En yuksek skora (veya saatlik kara) gore sirala
    flips.sort(key=lambda x: x.profit_per_hour, reverse=True)
    return flips[:limit] if limit is not None else flips
