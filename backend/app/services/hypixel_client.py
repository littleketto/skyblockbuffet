import httpx
from typing import Dict, Any, Optional
from app.core.config import settings


class HypixelClient:
    """
    Hypixel Skyblock Asenkron API Istemcisi (Client)
    Tum HTTP isteklerini tek bir merkezden, asenkron ve guvenli sekilde yonetir.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.HYPIXEL_API_KEY
        self.base_url = settings.HYPIXEL_API_BASE
        # Baglantilari canli tutup her istekte yeni el sikisma yapmamak icin Client olusturuyoruz
        self.headers = {"User-Agent": "SkyblockBuffet-Analyzer/1.0"}
        if self.api_key:
            self.headers["API-Key"] = self.api_key

    async def get_items(self) -> Dict[str, Any]:
        """
        Hypixel resmi esya listesini ceker (/resources/skyblock/items).
        Bu endpoint 5.600+ esyanin isimlerini, nadirliklerini ve NPC satis fiyatlarini icerir.
        Herkese aciktir (API Key gerektirmez).
        """
        url = f"{self.base_url}/resources/skyblock/items"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def get_bazaar(self) -> Dict[str, Any]:
        """
        Bazaar'daki anlik piyasa verilerini ceker (/skyblock/bazaar).
        2.200'den fazla pazar urununun anlik Insta-Buy, Insta-Sell,
        emir derinligi ve 7 gunluk hacim verilerini dondurur.
        Herkese aciktir (API Key gerektirmez).
        """
        url = f"{self.base_url}/skyblock/bazaar"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def get_auctions(self, page: int = 0) -> Dict[str, Any]:
        """
        Auction House'daki aktif muzayedeleri sayfali olarak ceker (/skyblock/auctions).
        Sayfa numarasi verilmezse ilk sayfayi (page=0) ve toplam sayfa adedini dondurur.
        """
        url = f"{self.base_url}/skyblock/auctions?page={page}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()


# Singleton Client ornegi (Proje genelinde ortak kullanilabilir)
hypixel_client = HypixelClient()
