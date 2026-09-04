import time
import httpx
from typing import Dict, Any, Optional

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
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url, headers=self.headers)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list) and len(data) > 0:
                        total_volume = sum(d.get("volume", 0) for d in data)
                        if total_volume > 0:
                            avg_price = sum(d.get("avg", 0) * d.get("volume", 0) for d in data) / total_volume
                            min_price = min(d.get("min", 0) for d in data if d.get("min", 0) > 0)
                            max_price = max(d.get("max", 0) for d in data)

                            result = {
                                "daily_volume": total_volume,
                                "avg_price": round(avg_price, 0),
                                "min_price": round(min_price, 0),
                                "max_price": round(max_price, 0),
                            }
                            # Cache'e kaydet
                            _cache[item_id] = {"timestamp": now, "data": result}
                            return result
        except Exception:
            pass

        return None


coflnet_service = CoflnetService()
