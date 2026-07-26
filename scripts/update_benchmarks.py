import pandas as pd
import os
from datetime import datetime, timedelta

DATA_PATH = "benchmarklar.parquet"

# İlk çalıştırmada (dosya hiç yoksa) kaç yıl geriye gidilsin
ILK_CALISTIRMA_YIL = 3

EVDS_SERIES = ["TP.DK.USD.A.YTL", "TP.DK.EUR.A.YTL", "TP.MK.F.BILESIK.TUM"]
EVDS_COLUMN_MAP = {
    "TP.DK.USD.A.YTL": "USD_Alis",
    "TP.DK.EUR.A.YTL": "EUR_Alis",
    "TP.MK.F.BILESIK.TUM": "BIST100",
}

# NOT: BIST-KYD 1 Aylık Mevduat TL Endeksi henüz otomatik çekilemiyor
# (borsapy'de yok, borsaistanbul.com sayfası JavaScript ile yükleniyor).
# Bulununca bu dosyaya "Mevduat_Endeksi" sütunu olarak eklenecek.


def fetch_evds_usd_eur_bist(start, end):
    import borsapy as bp

    api_key = os.environ.get("EVDS_API_KEY")
    if not api_key:
        raise RuntimeError("EVDS_API_KEY ortam değişkeni bulunamadı (GitHub Secrets'a eklenmiş mi?).")
    bp.set_evds_key(api_key)

    df = bp.evds_download(
        EVDS_SERIES,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        frequency="daily",
    )
    df = df.reset_index()
    df = df.rename(columns={df.columns[0]: "Tarih", **EVDS_COLUMN_MAP})
    df["Tarih"] = pd.to_datetime(df["Tarih"]).dt.normalize()
    return df[["Tarih", "USD_Alis", "EUR_Alis", "BIST100"]]


def fetch_gold(start, end):
    import borsapy as bp

    gold = bp.FX("gram-altin")
    df = gold.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    if df.empty:
        return pd.DataFrame(columns=["Tarih", "Altin_Gram"])
    df = df.reset_index()
    df = df.rename(columns={df.columns[0]: "Tarih", "Close": "Altin_Gram"})
    df["Tarih"] = pd.to_datetime(df["Tarih"]).dt.normalize()
    return df[["Tarih", "Altin_Gram"]]


def main():
    if os.path.exists(DATA_PATH):
        hist = pd.read_parquet(DATA_PATH)
        hist["Tarih"] = pd.to_datetime(hist["Tarih"]).dt.normalize()
        last_date = hist["Tarih"].max()
    else:
        hist = pd.DataFrame(columns=["Tarih", "USD_Alis", "EUR_Alis", "BIST100", "Altin_Gram"])
        last_date = pd.Timestamp(datetime.today().date()) - timedelta(days=365 * ILK_CALISTIRMA_YIL)

    start = last_date  # son günü de tekrar çek (kaynaklar bazen o günü sonradan düzeltiyor)
    end = pd.Timestamp(datetime.today().date())

    if start > end:
        print("Zaten güncel, yeni veri çekilmeyecek.")
        return

    try:
        evds_df = fetch_evds_usd_eur_bist(start, end)
    except Exception as e:
        print("EVDS (USD/EUR/BIST100) verisi çekilemedi:", e)
        evds_df = pd.DataFrame(columns=["Tarih", "USD_Alis", "EUR_Alis", "BIST100"])

    try:
        gold_df = fetch_gold(start, end)
    except Exception as e:
        print("Altın verisi çekilemedi:", e)
        gold_df = pd.DataFrame(columns=["Tarih", "Altin_Gram"])

    new = pd.merge(evds_df, gold_df, on="Tarih", how="outer")
    if new.empty:
        print("Bu aralıkta yeni veri yok (hafta sonu/tatil olabilir).")
        return

    hist_kept = hist[hist["Tarih"] < start]
    combined = pd.concat([hist_kept, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["Tarih"], keep="last")
    combined = combined.sort_values("Tarih")
    combined.to_parquet(DATA_PATH, index=False)
    print(f"Güncellendi. Toplam satır: {len(combined)}")


if __name__ == "__main__":
    main()
