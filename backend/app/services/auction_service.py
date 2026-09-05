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
    "Hyper", "Grand", "Odd", "Sharp", "Heavy", "Titanic", "Dirty", "Shimmer",
    "Fabled", "Suspicious", "Gentle", "Fair", "Epic", "Sharp", "Deadly",
    "Fine", "Grand", "Rich", "Magnetic", "Mighty", "Pure", "Smart",
    "Precise", "Spiritual", "Headstrong", "Strengthened", "Bustling", "Mossy",
    "Festive", "Lethal", "Heated", "Ambered", "Auspicious", "Fleet", "Stiff",
    "Lucky", "Very", "Highly", "Extremely", "Not", "Definitely"
]


def clean_minecraft_text(text: str) -> str:
    """Minecraft renk ve format kodlarini temizler."""
    if not text:
        return ""
    clean = re.sub(r"§[0-9a-fk-or]", "", text)
    clean = clean.replace("✪", "*")
    clean = clean.encode("ascii", "ignore").decode("ascii")
    return clean.strip()


CATEGORY_MAP = {
    "weapon": "weapons",
    "armor": "armor",
    "accessories": "accessories",
    "consumables": "consumables",
    "cosmetic": "cosmetics",
    "helmet_skins": "cosmetics",
    "other_skins": "cosmetics",
    "barn_skins": "cosmetics",
    "dyes": "cosmetics",
    "runes": "cosmetics",
    "misc": "tools_misc",
}


def normalize_category(raw_category: Optional[str], is_pet: bool = False) -> str:
    """Hypixel ham kategorilerini oyundaki 7 ana kategoriye esler."""
    if is_pet:
        return "pets"
    if not raw_category:
        return "tools_misc"
    return CATEGORY_MAP.get(raw_category.lower(), "tools_misc")


def extract_item_info_from_bytes(bytes_data: str) -> Dict[str, Any]:
    """
    Hypixel item_bytes NBT akisindan kesin oyun ici esya kodunu,
    pet bilgilerini ve Coflnet sorgu kodunu cikarir.
    """
    info: Dict[str, Any] = {
        "item_id": None,
        "coflnet_id": None,
        "is_pet": False,
        "pet_type": None,
        "pet_tier": None,
    }
    if not bytes_data:
        return info

    try:
        raw = gzip.decompress(base64.b64decode(bytes_data))

        # 1. Oncelikli Pet Kontrolu: Hypixel petInfo NBT blogu
        if b"petInfo" in raw:
            m_type = re.search(rb'"type":\s*"([A-Za-z0-9_]+)"', raw)
            m_tier = re.search(rb'"tier":\s*"([A-Za-z0-9_]+)"', raw)
            if m_type:
                ptype = m_type.group(1).decode("ascii", errors="ignore")
                ptier = m_tier.group(1).decode("ascii", errors="ignore") if m_tier else "COMMON"
                info["is_pet"] = True
                info["pet_type"] = ptype
                info["pet_tier"] = ptier
                # Pazar fiyati ve gruplama nadirlik seviyesine goredir
                info["item_id"] = f"PET_{ptype}_{ptier}"
                # Coflnet gecmis satis verisi PET_{ptype} altindadir
                info["coflnet_id"] = f"PET_{ptype}"
                return info

        # 2. Standart Esya 'id' NBT degeri
        m = re.search(rb"\x08\x00\x02id\x00[\x00-\xff]([A-Za-z0-9_]+)", raw)
        if m:
            item_id = m.group(1).decode("ascii", errors="ignore")
            # Eger id "PET" geldiyse ancak petInfo regexi ilk asamada yakalayamadiysa
            if item_id == "PET":
                m_type = re.search(rb'type.:.([A-Za-z0-9_]+)', raw)
                if m_type:
                    ptype = m_type.group(1).decode("ascii", errors="ignore")
                    info["is_pet"] = True
                    info["pet_type"] = ptype
                    info["item_id"] = f"PET_{ptype}"
                    info["coflnet_id"] = f"PET_{ptype}"
                    return info
            info["item_id"] = item_id
            info["coflnet_id"] = item_id
            return info
    except Exception:
        pass

    return info


def extract_item_id_from_bytes(bytes_data: str) -> Optional[str]:
    """Geriye uyumluluk icin temel item_id dondurur."""
    return extract_item_info_from_bytes(bytes_data).get("item_id")


def extract_clean_pet_name(name: str, tier: Optional[str] = None) -> str:
    """Pet isimlerindeki [Lvl XX] seviyelerini temizler ve nadirlik ekler."""
    clean = clean_minecraft_text(name)
    clean = re.sub(r"\[[Ll][Vv][Ll]\s*\d+\]\s*", "", clean).strip()
    if tier and tier.upper() != "COMMON":
        return f"{clean} ({tier.capitalize()})"
    return clean


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
        category: Optional[str] = None,
        limit: Optional[int] = None,
        fresh: bool = False,
    ) -> List[AHFlipItem]:
        """
        Auction House'taki tum esyalari kapsar:
        1. 40.000+ aktif ilani tarar, Petleri ve temel esya kimliklerini (item_id) ayiklar.
        2. 7 ana kategoriye (Weapons, Armor, Accessories, Pets, Consumables, Cosmetics, Tools & Misc) normalize eder.
        3. Her esya icin En Ucuz (LBIN), 2. En Ucuz (2nd BIN), kar ve getiri oranini hesaplar.
        4. Kategori bazinda veya genel pazarda yuksek karli adaylarin 24s gercek satis gecmisini Coflnet ile zenginlestirir.
        5. Tum sonuclari hafizada cache'leyerek aninda ve sayfali sekilde sunar.
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

                # 1. 40.000+ ilani temel esya kimligine (item_id) ve pet nadirligine gore grupla
                groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                display_names: Dict[str, str] = {}
                item_categories: Dict[str, str] = {}
                item_coflnet_ids: Dict[str, str] = {}

                for a in bin_auctions:
                    raw_name = a.get("item_name", "")
                    clean_name = clean_minecraft_text(raw_name)
                    if not clean_name:
                        continue

                    # NBT'den kesin oyun ici item bilgilerini cikar
                    info = extract_item_info_from_bytes(a.get("item_bytes", ""))
                    item_id = info.get("item_id")
                    if not item_id:
                        base_name = extract_base_item_name(clean_name)
                        item_id = base_name.upper().replace(" ", "_").replace("'", "")

                    groups[item_id].append(a)

                    # Kategori ve Coflnet ID belirle
                    is_pet = info.get("is_pet", False)
                    norm_cat = normalize_category(a.get("category"), is_pet=is_pet)
                    item_categories[item_id] = norm_cat
                    item_coflnet_ids[item_id] = info.get("coflnet_id") or item_id

                    # Kullaniciya gosterilecek baslik
                    if is_pet:
                        pet_display = extract_clean_pet_name(clean_name, info.get("pet_tier") or a.get("tier"))
                        if item_id not in display_names or len(pet_display) < len(display_names[item_id]):
                            display_names[item_id] = pet_display
                    else:
                        base_name = extract_base_item_name(clean_name)
                        if item_id not in display_names or len(base_name) < len(display_names[item_id]):
                            display_names[item_id] = base_name

                processed_items: List[Dict[str, Any]] = []

                for item_id, auctions in groups.items():
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
                        "name": display_names.get(item_id, extract_base_item_name(clean_minecraft_text(lbin_auc.get("item_name", item_id)))),
                        "item_id": item_id,
                        "coflnet_id": item_coflnet_ids.get(item_id, item_id),
                        "category": item_categories.get(item_id, "tools_misc"),
                        "lbin": lbin,
                        "second_lbin": second_lbin,
                        "target_sell": target_sell,
                        "profit": profit,
                        "margin": margin,
                        "lbin_auc": lbin_auc,
                        "total_listings": len(auctions),
                    })

                # En yuksek potansiyel kara gore sirala
                processed_items.sort(key=lambda x: x["profit"], reverse=True)

                # Pazardaki tum kar potansiyeli olan en iyi 400 adayin satis verilerini
                # Coflnet baglanti havuzuyla ~1.5 saniyede cek
                top_slice = processed_items[:400]
                top_ids = [c["coflnet_id"] for c in top_slice]
                histories_map = await coflnet_service.get_multiple_items_history_24h(top_ids, max_concurrent=25)

                enriched_flips: List[AHFlipItem] = []

                for c in processed_items:
                    history = histories_map.get(c["coflnet_id"])
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
                    else:
                        target_sell_price = c["target_sell"]
                        if profit > 5000000 and (second_lbin / max(1.0, lbin)) > 4.0:
                            liquidity_status = "RISKLI"
                            risk_warning = "2. BIN ile aradaki fark cok yuksek, manipule ilan olabilir."

                    # PPH (Profit Per Hour - Saatlik Tahmini Kar) Hesabi:
                    if daily_vol > 0 and profit > 0:
                        hourly_cap = max(0.1, (daily_vol / 24.0) * 0.15)
                        pph = round(profit * hourly_cap, 0)
                    else:
                        pph = 0.0

                    enriched_flips.append(
                        AHFlipItem(
                            item_name=c["name"],
                            item_id=c["item_id"],
                            tier=c["lbin_auc"].get("tier"),
                            category=c["category"],
                            lowest_bin=round(lbin, 0),
                            second_lowest_bin=round(second_lbin, 0),
                            target_sell_price=round(target_sell_price, 0),
                            net_profit=round(profit, 0),
                            margin_percent=round(margin, 1),
                            profit_per_hour=pph,
                            total_listings=c["total_listings"],
                            auction_uuid=c["lbin_auc"].get("uuid", ""),
                            daily_volume=daily_vol,
                            avg_sold_price=avg_price,
                            liquidity_status=liquidity_status,
                            risk_warning=risk_warning,
                        )
                    )

                # Nihai siralama:
                # 1. Gercekten hacmi olan ve PPH ureten likit esyalar en uste cikar.
                # 2. Hacmi 0 olan sahte / manipule fiyatlar geriye duser.
                enriched_flips.sort(key=lambda x: (x.profit_per_hour, x.net_profit), reverse=True)
                self._cached_flips = enriched_flips
                self._last_fetch_time = time.time()
                all_items = self._cached_flips

        # Filtreleme (Client istegine gore)
        filtered = []
        target_cat = category.lower().strip() if category else None
        if target_cat in ["all", "tumu", "all_categories", ""]:
            target_cat = None

        for item in all_items:
            if target_cat and item.category != target_cat:
                continue
            if max_budget is not None and item.lowest_bin > max_budget:
                continue
            if min_profit > 0 and item.net_profit < min_profit:
                continue
            if min_margin > 0 and item.margin_percent < min_margin:
                continue
            filtered.append(item)

        return filtered[:limit] if limit is not None else filtered


auction_service = AuctionService()
