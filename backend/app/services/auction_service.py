import re
import asyncio
import httpx
from collections import defaultdict
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.schemas.auction import AHFlipItem


def clean_minecraft_text(text: str) -> str:
    """Minecraft renk ve format kodlarini (§a, §c vb.) ve ASCII disi sembolleri temizler."""
    if not text:
        return ""
    # 1. Minecraft renk kodlarini kaldir (§a, §e, §l vb.)
    clean = re.sub(r"§[0-9a-fk-or]", "", text)
    # 2. Yildiz (✪) gibi ozel karakterleri standart yıldıza cevir veya temizle
    clean = clean.replace("✪", "*")
    # 3. Kalan ASCII disi ozel karakterleri temizle
    clean = clean.encode("ascii", "ignore").decode("ascii")
    return clean.strip()


class AuctionService:
    """
    Hypixel Auction House (AH) Tarayicisi ve Sniping / Flipping Motoru
    Tum aktif muzayede sayfalarini paralel (asenkron) olarak saniyeler icinde tarar,
    Lowest BIN (LBIN) firsatlarini yakalar.
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
        """
        Tum sayfali aktif muzayedeleri paralel olarak ceker ve sadece BIN (Buy It Now) olanlari suzer.
        """
        print("Auction House: Sayfa 0 taranarak toplam sayfa adedi ogreniliyor...")
        sem = asyncio.Semaphore(max_concurrent)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)

        async with httpx.AsyncClient(limits=limits) as client:
            res = await client.get(f"{self.base_url}/skyblock/auctions?page=0", headers=self.headers, timeout=15.0)
            res.raise_for_status()
            data = res.json()
            total_pages = data.get("totalPages", 1)
            all_auctions = data.get("auctions", [])

            print(f"Auction House: Toplam {total_pages} sayfa ({data.get('totalAuctions')} ilan) bulundu. Paralel taranıyor...")

            tasks = [self._fetch_page(client, p, sem) for p in range(1, total_pages)]
            results = await asyncio.gather(*tasks)

            for page_auctions in results:
                all_auctions.extend(page_auctions)

            bin_auctions = [a for a in all_auctions if a.get("bin", False)]
            print(f"Auction House: Toplam {len(bin_auctions)} adet BIN ilani analiz icin hazir.")
            return bin_auctions

    async def calculate_ah_flips(
        self,
        min_profit: float = 100000.0,
        min_margin: float = 15.0,
        min_listings: int = 3,
        max_price_ratio: float = 4.0, # 2. LBIN fiyatinin 1. LBIN'e orani max 4x olmali
        max_budget: Optional[float] = None,
        limit: int = 50,
    ) -> List[AHFlipItem]:
        """
        AH Sniping / Flipping Hesaplayicisi:
        1. Esyalari isimlerine gore gruplar.
        2. Fiyatlari kucukten buyuge siralar (1. LBIN vs 2. LBIN).
        3. Fiyat manipülasyonunu engellemek icin ilan sayisi ve fiyat artis oranini filtreler.
        4. %2 AH vergisi dusulerek net kar ve ROI hesaplanir.
        """
        bin_auctions = await self.fetch_all_bin_auctions()
        if not bin_auctions:
            return []

        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for a in bin_auctions:
            raw_name = a.get("item_name", "")
            clean_name = clean_minecraft_text(raw_name)
            if clean_name:
                groups[clean_name].append(a)

        flips: List[AHFlipItem] = []

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

            target_sell_price = second_lbin * 0.99
            net_revenue = target_sell_price * 0.98
            profit = net_revenue - lbin

            if profit < min_profit:
                continue

            margin_percent = (profit / lbin) * 100.0
            if margin_percent < min_margin:
                continue

            flips.append(
                AHFlipItem(
                    item_name=name,
                    tier=lbin_auc.get("tier"),
                    category=lbin_auc.get("category"),
                    lowest_bin=round(lbin, 0),
                    second_lowest_bin=round(second_lbin, 0),
                    target_sell_price=round(target_sell_price, 0),
                    net_profit=round(profit, 0),
                    margin_percent=round(margin_percent, 1),
                    total_listings=len(auctions),
                    auction_uuid=lbin_auc.get("uuid", ""),
                )
            )

        flips.sort(key=lambda x: x.net_profit, reverse=True)
        return flips[:limit]


auction_service = AuctionService()
