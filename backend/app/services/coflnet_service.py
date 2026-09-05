import time
import httpx
import asyncio
from typing import Dict, Any, Optional, List

# Bellek ici Onbellek (Cache): 10 dakika (600 saniye) boyunca sonuclari saklar
# Boylece Coflnet API'sine ayni esya icin tekrar tekrar istek atilmaz.
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 600


class CoflnetService:
    """
    Skyblock Toplulugu Satis Gecmisi API Istemcisi (Coflnet)
    Herhangi bir esyanin son 24 saatteki ve 1 haftadaki gercek satis adetlerini (Volume)
    ve ortalama satildigi fiyati (Avg Price) getirir.
    """

    def __init__(self):
        self.base_url = "https://sky.coflnet.com/api/item/price"
        self.headers = {"User-Agent": "SkyblockBuffet-Analyzer/1.0"}

    async def get_item_history_24h(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Bir esyanin son 24 saatteki satis istatistiklerini dondurur.
        Dönen sozluk:
        - daily_volume: 24 saatte toplam kac adet satildi
        - avg_price: Ortalama satis fiyati
        - min_price: En ucuz satis fiyati
        - max_price: En pahali satis fiyati
        """
        if not item_id:
            return None

        # Onbellek Kontrolu
        now = time.time()
        cached = _cache.get(item_id)
        if cached and (now - cached["timestamp"]) < CACHE_TTL:
            return cached["data"]

        url = f"{self.base_url}/{item_id}/history/day"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=7.0) as client:
                    res = await client.get(url, headers=self.headers)
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, list) and len(data) > 0:
                            total_volume = sum(d.get("volume", 0) for d in data if d.get("volume"))
                            if total_volume > 0:
                                avg_price = sum(d.get("avg", 0) * d.get("volume", 0) for d in data) / total_volume
                                valid_mins = [d.get("min", 0) for d in data if d.get("min", 0) and d.get("min", 0) > 0]
                                min_price = min(valid_mins) if valid_mins else avg_price
                                valid_maxs = [d.get("max", 0) for d in data if d.get("max", 0) and d.get("max", 0) > 0]
                                max_price = max(valid_maxs) if valid_maxs else avg_price

                                result = {
                                    "daily_volume": int(total_volume),
                                    "avg_price": round(avg_price, 0),
                                    "min_price": round(min_price, 0),
                                    "max_price": round(max_price, 0),
                                }
                                # Cache'e kaydet
                                _cache[item_id] = {"timestamp": now, "data": result}
                                return result
                        return None
                    elif res.status_code in (403, 429):
                        await asyncio.sleep(0.3 * (attempt + 1))
                        continue
                    else:
                        return None
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.3)
                pass

        return None

    async def get_multiple_items_history_24h(
        self, item_ids: List[str], max_concurrent: int = 8
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Birden fazla esyanin 24 saatlik verisini baglanti havuzu ve semaforla cok hizli sekilde ceker.
        Zaten onbellekte olan esyalar icin ag istegi yapilmaz.
        """
        now = time.time()
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        missing_ids: List[str] = []

        for iid in item_ids:
            if not iid:
                continue
            cached = _cache.get(iid)
            if cached and (now - cached["timestamp"]) < CACHE_TTL:
                results[iid] = cached["data"]
            else:
                missing_ids.append(iid)

        if not missing_ids:
            return results

        # Eksik olanlari paralel cek
        sem = asyncio.Semaphore(max_concurrent)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=25)

        async def _fetch_single(client: httpx.AsyncClient, iid: str):
            async with sem:
                url = f"{self.base_url}/{iid}/history/day"
                for attempt in range(3):
                    try:
                        res = await client.get(url, headers=self.headers)
                        if res.status_code == 200:
                            data = res.json()
                            if isinstance(data, list) and len(data) > 0:
                                total_volume = sum(d.get("volume", 0) for d in data if d.get("volume"))
                                if total_volume > 0:
                                    avg_price = sum(d.get("avg", 0) * d.get("volume", 0) for d in data) / total_volume
                                    valid_mins = [d.get("min", 0) for d in data if d.get("min", 0) and d.get("min", 0) > 0]
                                    min_price = min(valid_mins) if valid_mins else avg_price
                                    valid_maxs = [d.get("max", 0) for d in data if d.get("max", 0) and d.get("max", 0) > 0]
                                    max_price = max(valid_maxs) if valid_maxs else avg_price

                                    r = {
                                        "daily_volume": int(total_volume),
                                        "avg_price": round(avg_price, 0),
                                        "min_price": round(min_price, 0),
                                        "max_price": round(max_price, 0),
                                    }
                                    _cache[iid] = {"timestamp": time.time(), "data": r}
                                    results[iid] = r
                                    return
                            results[iid] = None
                            return
                        elif res.status_code in (403, 429):
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        else:
                            results[iid] = None
                            return
                    except Exception:
                        if attempt < 2:
                            await asyncio.sleep(0.2)
                        pass
                results[iid] = None

        async with httpx.AsyncClient(limits=limits, timeout=8.0) as client:
            tasks = [_fetch_single(client, iid) for iid in missing_ids]
            await asyncio.gather(*tasks)

        return results

    async def get_bazaar_history(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Bir Bazaar esyasinin son 24 saat ve son 1 haftalik Insta-Buy / Insta-Sell
        fiyat ortalamalarini ve grafik noktalarini Coflnet'ten ceker.
        """
        if not item_id:
            return None

        now = time.time()
        cache_key = f"bazaar_hist_{item_id}"
        cached = _cache.get(cache_key)
        if cached and (now - cached["timestamp"]) < CACHE_TTL:
            return cached["data"]

        headers = {"User-Agent": "SkyblockBuffet-Analyzer/1.0"}
        async with httpx.AsyncClient(timeout=6.0) as client:
            try:
                # Son 24 saatlik veriler
                res_day = await client.get(f"https://sky.coflnet.com/api/bazaar/{item_id}/history/day", headers=headers)
                day_data = res_day.json() if res_day.status_code == 200 else []

                # Son 7 gunluk veriler
                res_week = await client.get(f"https://sky.coflnet.com/api/bazaar/{item_id}/history/week", headers=headers)
                week_data = res_week.json() if res_week.status_code == 200 else []

                # 24s ortalamalari
                buy_24h = [x["buy"] for x in day_data if x.get("buy")]
                sell_24h = [x["sell"] for x in day_data if x.get("sell")]
                avg_buy_24h = round(sum(buy_24h) / len(buy_24h), 1) if buy_24h else None
                avg_sell_24h = round(sum(sell_24h) / len(sell_24h), 1) if sell_24h else None

                # 7g ortalamalari
                buy_7d = [x["buy"] for x in week_data if x.get("buy")]
                sell_7d = [x["sell"] for x in week_data if x.get("sell")]
                avg_buy_7d = round(sum(buy_7d) / len(buy_7d), 1) if buy_7d else None
                avg_sell_7d = round(sum(sell_7d) / len(sell_7d), 1) if sell_7d else None

                # 24s grafik noktalari (Zaman sirasina gore: eskiden yeniye dogru)
                # day_data yeninden eskiye siralidir, ters cevirip ornekleyelim
                chronological_points = list(reversed(day_data))
                # Maksimum 35 nokta goster (grafik sade ve anlasilir olsun)
                step = max(1, len(chronological_points) // 35)
                sampled_points = chronological_points[::step]

                result = {
                    "item_id": item_id,
                    "avg_buy_24h": avg_buy_24h,     # 24s Insta-Buy (Sell Offer) ortalamasi
                    "avg_sell_24h": avg_sell_24h,   # 24s Insta-Sell (Buy Order) ortalamasi
                    "min_buy_24h": min(buy_24h) if buy_24h else None,
                    "max_buy_24h": max(buy_24h) if buy_24h else None,
                    "min_sell_24h": min(sell_24h) if sell_24h else None,
                    "max_sell_24h": max(sell_24h) if sell_24h else None,
                    "avg_buy_7d": avg_buy_7d,       # 7 Gunluk Insta-Buy ortalamasi
                    "avg_sell_7d": avg_sell_7d,     # 7 Gunluk Insta-Sell ortalamasi
                    "points_24h": [{"t": x.get("timestamp"), "buy": x.get("buy"), "sell": x.get("sell")} for x in sampled_points],
                }

                _cache[cache_key] = {"timestamp": now, "data": result}
                return result
            except Exception as e:
                print(f"Coflnet bazaar history hatasi ({item_id}):", e)
                return None


coflnet_service = CoflnetService()
