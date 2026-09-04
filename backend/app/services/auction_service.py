import re
import asyncio
import httpx
from collections import defaultdict
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.schemas.auction import AHFlipItem
from app.services.coflnet_service import coflnet_service

REFORGES = [
    "Fierce", "Spicy", "Heroic", "Withered", "Necrotic", "Clean", "Fast",
    "Ancient", "Giant", "Loving", "Wise", "Renowned", "Submerged", "Jaded",
    "Hyper", "Grand", "Odd", "Sharp", "Heavy", "Titanic", "Dirty", "Shimmer"
]


def clean_minecraft_text(text: str) -> str:
    """Minecraft renk ve format kodlarini temizler."""
    if not text:
        return ""
    clean = re.sub(r"§[0-9a-fk-or]", "", text)
    clean = clean.replace("✪", "*")
    clean = clean.encode("ascii", "ignore").decode("ascii")
    return clean.strip()


def extract_base_item_name(name: str) -> str:
    """Reforgelari ve yıldızları ayıklayarak saf eşya adını bulur."""
    clean = re.sub(r"[\*\✪\§]+", "", name).strip()
    for r in REFORGES:
        if clean.lower().startswith(r.lower() + " "):
            clean = clean[len(r) + 1 :].strip()
            break
    return clean


class AuctionService:
    """
    Hypixel Auction House (AH) Tarayicisi ve Gecmis Satis Destekli Sniping Motoru
    """

    def __init__(self):
        self.base_url = settings.HYPIXEL_API_BASE
        self.headers = {"User-Agent": "SkyblockBuffet-Analyzer/1.0"}
        if settings.HYPIXEL_API_KEY:
            self.headers["API-Key"] = settings.HYPIXEL_API_KEY

    async def _fetch_page(self, client: httpx.AsyncClient, page: int, sem: asyncio.Semaphore) -> List[Dict[str, Any]]:
        async with sem:
            try:
                url = f"{self.base_url}/skyblock/auctions?page={page}"
                res = await client.get(url, headers=self.headers, timeout=15.0)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("auctions", [])
            except Exception:
                pass
            return []

    async def fetch_all_bin_auctions(self, max_concurrent: int = 15) -> List[Dict[str, Any]]:
        """Tum aktif BIN ilanlarini asenkron ve paralel olarak ceker."""
        sem = asyncio.Semaphore(max_concurrent)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)

        async with httpx.AsyncClient(limits=limits) as client:
            res = await client.get(f"{self.base_url}/skyblock/auctions?page=0", headers=self.headers, timeout=15.0)
            res.raise_for_status()
            data = res.json()
            total_pages = data.get("totalPages", 1)
            all_auctions = data.get("auctions", [])

            tasks = [self._fetch_page(client, p, sem) for p in range(1, total_pages)]
            results = await asyncio.gather(*tasks)

            for page_auctions in results:
                all_auctions.extend(page_auctions)

            return [a for a in all_auctions if a.get("bin", False)]

    async def calculate_ah_flips(
        self,
        min_profit: float = 100000.0,
        min_margin: float = 15.0,
        min_listings: int = 2,
        max_price_ratio: float = 4.0,
        max_budget: Optional[float] = None,
        limit: int = 50,
    ) -> List[AHFlipItem]:
        """
        AH Sniping ve Gecmis Satis Analizi:
        1. Aktif LBIN ve 2. LBIN'i karsilastirir.
        2. Coflnet gecmis satis veritabanindan son 24 saatlik satis adedi (Volume)
           ve ortalama satis fiyatini (Real Avg) ceker.
        3. Kar projeksiyonunu yapay 2. LBIN yerine gercek satis fiyatina gore dogrular!
        """
        bin_auctions = await self.fetch_all_bin_auctions()
        if not bin_auctions:
            return []

        # Isimlerine gore grupla
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for a in bin_auctions:
            raw_name = a.get("item_name", "")
            clean_name = clean_minecraft_text(raw_name)
            if clean_name:
                groups[clean_name].append(a)

        candidates: List[Dict[str, Any]] = []

        for name, auctions in groups.items():
            if len(auctions) < min_listings:
                continue

            auctions.sort(key=lambda x: float(x.get("starting_bid", 0)))
            lbin_auc = auctions[0]
            second_auc = auctions[1]

            lbin = float(lbin_auc.get("starting_bid", 0))
            second_lbin = float(second_auc.get("starting_bid", 0))

            if lbin <= 5000 or second_lbin <= lbin:
                continue

            if (second_lbin / lbin) > max_price_ratio:
                continue

            if max_budget is not None and lbin > max_budget:
                continue

            candidates.append({
                "name": name,
                "base_name": extract_base_item_name(name),
                "lbin": lbin,
                "second_lbin": second_lbin,
                "lbin_auc": lbin_auc,
                "total_listings": len(auctions),
            })

        # Kar marjina gore ilk 20 adayi sec ve gecmis verilerini paralel sorgula
        candidates.sort(key=lambda x: (x["second_lbin"] - x["lbin"]), reverse=True)
        top_candidates = candidates[:30]

        flips: List[AHFlipItem] = []

        for c in top_candidates:
            base_name = c["base_name"]
            item_id_guess = base_name.upper().replace(" ", "_").replace("'", "")

            # Coflnet'ten son 24 saatlik veriyi cek
            history = await coflnet_service.get_item_history_24h(item_id_guess)

            lbin = c["lbin"]
            second_lbin = c["second_lbin"]

            daily_vol = 0
            avg_price = None
            liquidity_status = "ORTA"
            risk_warning = None

            if history:
                daily_vol = history.get("daily_volume", 0)
                avg_price = history.get("avg_price")

                if daily_vol >= 15:
                    liquidity_status = "YUKSEK"
                elif daily_vol >= 3:
                    liquidity_status = "ORTA"
                else:
                    liquidity_status = "RISKLI"
                    risk_warning = f"Son 24 saatte sadece {daily_vol} adet satildi! Dikkatli olun."

                # Gercekci Satis Fiyati: 2. LBIN, gercek ortalamanin cok ustundeyse ortalama fiyata gore hesapla
                if avg_price and second_lbin > (avg_price * 1.20):
                    target_sell_price = round(avg_price * 1.02, 0)
                else:
                    target_sell_price = round(second_lbin * 0.99, 0)
            else:
                target_sell_price = round(second_lbin * 0.99, 0)
                liquidity_status = "ORTA"

            # Net Kar: %2 AH kesintisi
            net_revenue = target_sell_price * 0.98
            profit = net_revenue - lbin

            if profit < min_profit:
                continue

            margin_percent = (profit / lbin) * 100.0
            if margin_percent < min_margin:
                continue

            flips.append(
                AHFlipItem(
                    item_name=c["name"],
                    item_id=item_id_guess,
                    tier=c["lbin_auc"].get("tier"),
                    category=c["lbin_auc"].get("category"),
                    lowest_bin=round(lbin, 0),
                    second_lowest_bin=round(second_lbin, 0),
                    target_sell_price=round(target_sell_price, 0),
                    net_profit=round(profit, 0),
                    margin_percent=round(margin_percent, 1),
                    total_listings=c["total_listings"],
                    auction_uuid=c["lbin_auc"].get("uuid", ""),
                    daily_volume=daily_vol,
                    avg_sold_price=avg_price,
                    liquidity_status=liquidity_status,
                    risk_warning=risk_warning,
                )
            )

        flips.sort(key=lambda x: x.net_profit, reverse=True)
        return flips[:limit]


auction_service = AuctionService()
