import requests
import pandas as pd
from datetime import datetime

DATA_PATH = "tefas_acik_fonlar.parquet"
URL = "https://www.tefas.gov.tr/api/statistics/tefas/getFplFonList"


def main():
    print("TEFAS'a açık fon listesi çekiliyor...")
    try:
        resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"Hata: liste çekilemedi ({e}). Dosya güncellenmedi.")
        return

    data = payload.get("data") or []
    if not data:
        print("Uyarı: API'den boş liste döndü. Dosya güncellenmedi (eski veri korunuyor).")
        return

    df = pd.DataFrame(data)
    # Sadece ihtiyacımız olan kolonları tutuyoruz
    df = df.rename(columns={"fonKod": "Fon Kodu", "unvan": "Fon Unvanı", "durum": "Durum"})
    df = df[["Fon Kodu", "Fon Unvanı", "Durum"]].drop_duplicates(subset=["Fon Kodu"])
    df["Guncelleme_Tarihi"] = datetime.today().strftime("%Y-%m-%d")

    df.to_parquet(DATA_PATH, index=False)
    print(f"✅ {len(df)} adet TEFAS'a açık fon kaydedildi -> {DATA_PATH}")
    print("Not: Bu listede OLMAYAN her fon kodu TEFAS'a kapalı sayılır "
          "(getFplFonList sadece açık fonları döndürüyor).")


if __name__ == "__main__":
    main()
