import pandas as pd
from tefasfon import get_portfolio
from datetime import datetime
import os

DATA_PATH = "tefas_portfoy_dagilim.parquet"

# Kısaltmalardan Orijinal Türkçe Başlıklara Çeviri
KOLON_MAP = {
    "fonKodu": "Fon Kodu",
    "fonUnvan": "Fon Ünvanı",
    "tarih": "Tarih",
    "hs": "Hisse Senedi (%)",
    "yhs": "Yabancı Hisse Senedi (%)",
    "dt": "Devlet Tahvili (%)",
    "hb": "Hazine Bonosu (%)",
    "vdm": "Vadeli Mevduat (%)",
    "vmtl": "TL Vadeli Mevduat (%)",
    "tr": "Ters Repo (%)",
    "byf": "Borsa Yatırım Fonu (%)",
    "yyf": "Yabancı Yatırım Fonu (%)",
    "km": "Kıymetli Maden (%)",
    "kkstl": "TL Kira Sertifikası (%)",
    "osks": "Özel Sektör Kira Sertifikası (%)",
}


def main():
    bugun = datetime.today().strftime("%d.%m.%Y")

    # Eski veri varsa oku
    if os.path.exists(DATA_PATH):
        hist = pd.read_parquet(DATA_PATH)
        print(f"Eski veri yüklendi: {len(hist)} satır")
    else:
        hist = pd.DataFrame()
        print("Yeni veri dosyası oluşturulacak.")

    print(f"Bugünün tarihi: {bugun}")
    print("TEFAS'tan portföy dağılımı çekiliyor...")

    try:
        df = get_portfolio(fund_type="SEC", start_date=bugun, end_date=bugun)
    except Exception as e:
        print(f"Hata oluştu (muhtemelen tatil/hafta sonu): {e}")
        return

    if df is None or df.empty:
        print("Bugün için portföy verisi bulunamadı (tatil/hafta sonu olabilir).")
        return

    # Sadece sayısal kolonları yüzde formatına çevir
    sayisal_kolonlar = [k for k in KOLON_MAP.keys() if k not in ["fonKodu", "fonUnvan", "tarih"]]
    for kol in sayisal_kolonlar:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")

    # Türkçe başlıklara çevir
    df = df.rename(columns=KOLON_MAP)

    # Sadece mapping'te olan kolonları tut
    mevcut_kolonlar = [KOLON_MAP[k] for k in KOLON_MAP if k in df.columns or k in ["fonKodu", "fonUnvan", "tarih"]]
    df = df[[k for k in mevcut_kolonlar if k in df.columns]]

    # Yeni veriyi eski veriye ekle
    combined = pd.concat([hist, df], ignore_index=True)

    # Aynı Fon Kodu + Tarih kombinasyonundan tekrarları kaldır (son geleni tut)
    combined = combined.drop_duplicates(subset=["Fon Kodu", "Tarih"], keep="last")
    combined = combined.sort_values(["Fon Kodu", "Tarih"])

    combined.to_parquet(DATA_PATH, index=False)

    yeni_satir = len(df)
    toplam_satir = len(combined)
    print(f"✅ {yeni_satir} yeni satır eklendi. Toplam: {toplam_satir} satır.")


if __name__ == "__main__":
    main()
