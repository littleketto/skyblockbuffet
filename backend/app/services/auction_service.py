import re
import base64
import gzip
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


def extract_item_id_from_bytes(bytes_data: str) -> Optional[str]:
    """Hypixel item_bytes NBT akisindan kesin oyun ici esya kodunu cikarir."""
    if not bytes_data:
        return None
    try:
        raw = gzip.decompress(base64.b64decode(bytes_data))
        # NBT Tag_String 'id' degeri
        m = re.search(rb"\x08\x00\x02id\x00.([A-Za-z0-9_]+)", raw)
        if m:
            return m.group(1).decode("ascii", errors="ignore")
        # Pet esyalari icin petInfo kontrolu
        m_pet = re.search(rb"type.:.([A-Za-z0-9_]+)", raw)
        if m_pet:
            return f"{m_pet.group(1).decode('ascii', errors='ignore')}_PET"
    except Exception:
        pass
    return None


def extract_base_item_name(name: str) -> str:
    """Reforgelari ve yildizlari ayiklayarak saf esya adini bulur."""
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

        self._cached_flips: List[AHFlipItem] = []
        self._last_fetch_time: float = 0.0
        self._cache_lock = asyncio.Lock()
        self.CACHE_TTL: float = 30.0  # 30 saniye boyunca hafızadaki tüm taranmış AH'yi kullan

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
        limits = httpx.Limits(max_keepalive_connections=25, max_connections=35)

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
        min_profit: float = 0.0,
        min_margin: float = 0.0,
        min_listings: int = 1,
        max_price_ratio: float = 50.0,
        max_budget: Optional[float] = None,
        limit: Optional[int] = None,
        fresh: bool = False,
    ) -> List[AHFlipItem]:
        """
        Auction House'taki tum esyalari kapsar:
        1. 40.000+ aktif ilani tarar ve temiz esya isimlerine gore gruplar (5.600+ farkli esya).
        2. Her esya icin En Ucuz (LBIN), 2. En Ucuz (2nd BIN), kar ve getiri oranini hesaplar.
        3. En yuksek kar potansiyeline sahip ilk adaylarin 24s gercek satis gecmisini Coflnet ile zenginlestirir.
        4. Tum sonuclari hafizada cache'leyerek aninda ve sayfali sekilde sunar.
        """
        import time
        now = time.time()

        async with self._cache_lock:
            if not fresh and self._cached_flips and (now - self._last_fetch_time) < self.CACHE_TTL:
                all_items = self._cached_flips
            else:
                bin_auctions = await self.fetch_all_bin_auctions()
                if not bin_auctions:
                    return self._cached_flips or []

                # Isimlerine gore grupla
                groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for a in bin_auctions:
                    raw_name = a.get("item_name", "")
                    clean_name = clean_minecraft_text(raw_name)
                    if clean_name:
                        groups[clean_name].append(a)

                processed_items: List[Dict[str, Any]] = []

                for name, auctions in groups.items():
                    if len(auctions) < min_listings:
                        continue

                    auctions.sort(key=lambda x: float(x.get("starting_bid", 0)))
                    lbin_auc = auctions[0]
                    lbin = float(lbin_auc.get("starting_bid", 0))

                    if lbin <= 0:
                        continue

                    has_second = len(auctions) > 1
                    second_auc = auctions[1] if has_second else lbin_auc
                    second_lbin = float(second_auc.get("starting_bid", 0)) if has_second else lbin

                    # NBT'den kesin item_id'yi cikar
                    nbt_id = extract_item_id_from_bytes(lbin_auc.get("item_bytes", ""))
                    if not nbt_id:
                        base_name = extract_base_item_name(name)
                        nbt_id = base_name.upper().replace(" ", "_").replace("'", "")

                    # Hedef Satis Fiyati ve Kar
                    if has_second and second_lbin > lbin:
                        target_sell = round(second_lbin * 0.99, 0)
                        # Net Gelir = Satis * 0.98 (%2 AH vergisi)
                        net_revenue = target_sell * 0.98
                        profit = round(net_revenue - lbin, 0)
                        margin = round((profit / lbin) * 100.0, 1) if lbin > 0 else 0.0
                    else:
                        target_sell = lbin
                        profit = 0.0
                        margin = 0.0

                    processed_items.append({
                        "name": name,
                        "item_id": nbt_id,
                        "lbin": lbin,
                        "second_lbin": second_lbin,
                        "target_sell": target_sell,
                        "profit": profit,
                        "margin": margin,
                        "lbin_auc": lbin_auc,
                        "total_listings": len(auctions),
                    })

                # En yuksek kara gore sirala
                processed_items.sort(key=lambda x: x["profit"], reverse=True)

                # En yuksek karli ilk 40 esyanin gecmisini Coflnet'ten asenkron zenginlestir
                top_slice = processed_items[:40]
                history_tasks = [coflnet_service.get_item_history_24h(c["item_id"]) for c in top_slice]
                histories = await asyncio.gather(*history_tasks)

                enriched_flips: List[AHFlipItem] = []

                for idx, c in enumerate(processed_items):
                    history = histories[idx] if idx < len(histories) else None
                    lbin = c["lbin"]
                    second_lbin = c["second_lbin"]
                    profit = c["profit"]
                    margin = c["margin"]

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
                            risk_warning = f"Son 24 saatte sadece {daily_vol} adet satildi."

                        # Eger 2. LBIN ortalamanin %25 ustundeyse gercek ortalamaya gore kar duzelt
                        if avg_price and second_lbin > (avg_price * 1.25):
                            target_sell_price = round(avg_price * 1.02, 0)
                            profit = round((target_sell_price * 0.98) - lbin, 0)
                            margin = round((profit / lbin) * 100.0, 1) if lbin > 0 else 0.0
                    else:
                        target_sell_price = c["target_sell"]
                        if profit > 5000000 and (second_lbin / max(1.0, lbin)) > 4.0:
                            liquidity_status = "RISKLI"
                            risk_warning = "2. BIN ile aradaki fark cok yuksek, manipule ilan olabilir."

                    enriched_flips.append(
                        AHFlipItem(
                            item_name=c["name"],
                            item_id=c["item_id"],
                            tier=c["lbin_auc"].get("tier"),
                            category=c["lbin_auc"].get("category"),
                            lowest_bin=round(lbin, 0),
                            second_lowest_bin=round(second_lbin, 0),
                            target_sell_price=round(target_sell_price, 0),
                            net_profit=round(profit, 0),
                            margin_percent=round(margin, 1),
                            total_listings=c["total_listings"],
                            auction_uuid=c["lbin_auc"].get("uuid", ""),
                            daily_volume=daily_vol,
                            avg_sold_price=avg_price,
                            liquidity_status=liquidity_status,
                            risk_warning=risk_warning,
                        )
                    )

                # Nihai siralama: Once net kara gore sirala
                enriched_flips.sort(key=lambda x: (x.net_profit, x.margin_percent), reverse=True)
                self._cached_flips = enriched_flips
                self._last_fetch_time = time.time()
                all_items = self._cached_flips

        # Filtreleme (Client istegine gore)
        filtered = []
        for item in all_items:
            if max_budget is not None and item.lowest_bin > max_budget:
                continue
            if min_profit > 0 and item.net_profit < min_profit:
                continue
            if min_margin > 0 and item.margin_percent < min_margin:
                continue
            filtered.append(item)

        return filtered[:limit] if limit is not None else filtered


auction_service = AuctionService()
