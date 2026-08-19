import requests
import pandas as pd
import time
from datetime import datetime

DATA_PATH = "tefas_acik_fonlar.parquet"
URL = "https://www.tefas.gov.tr/api/statistics/tefas/getFplFonList"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
    "Origin": "https://www.tefas.gov.tr",
    "X-Requested-With": "XMLHttpRequest",
}


def fetch_liste():
    """Önce GET, olmazsa POST dener; birkaç kez tekrar dener (TEFAS'ın uç noktası
    bazen yanıt vermeden zaman aşımına uğratıyor — bot koruması olabilir)."""
    for deneme in range(1, 4):
        for method in ("GET", "POST"):
            try:
                if method == "GET":
                    resp = requests.get(URL, headers=HEADERS, timeout=60)
                else:
                    resp = requests.post(URL, headers=HEADERS, json={}, timeout=60)
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data") or []
                if data:
                    print(f"  Başarılı ({method}, {deneme}. deneme).")
                    return data
                print(f"  {method} boş veri döndürdü (deneme {deneme}).")
            except Exception as e:
                print(f"  {method} başarısız (deneme {deneme}): {e}")
        time.sleep(5)
    return None


def main():
    print("TEFAS'a açık fon listesi çekiliyor...")
    data = fetch_liste()
    if not data:
        print("Hata: liste hiçbir yöntemle çekilemedi. Dosya güncellenmedi (eski veri korunuyor).")
        return

    df = pd.DataFrame(data)
    df = df.rename(columns={"fonKod": "Fon Kodu", "unvan": "Fon Unvanı", "durum": "Durum"})
    df = df[["Fon Kodu", "Fon Unvanı", "Durum"]].drop_duplicates(subset=["Fon Kodu"])
    df["Guncelleme_Tarihi"] = datetime.today().strftime("%Y-%m-%d")

    df.to_parquet(DATA_PATH, index=False)
    print(f"✅ {len(df)} adet TEFAS'a açık fon kaydedildi -> {DATA_PATH}")


if __name__ == "__main__":
    main()
