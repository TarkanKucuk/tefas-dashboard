import pandas as pd
import os
from datetime import datetime, timedelta

DATA_PATH = "benchmarklar.parquet"

# İlk çalıştırmada (dosya hiç yoksa) kaç yıl geriye gidilsin
ILK_CALISTIRMA_YIL = 3

SERIES = ["TP.DK.USD.A.YTL", "TP.DK.EUR.A.YTL", "TP.MK.F.BILESIK"]
COLUMN_MAP = {
    "TP_DK_USD_A_YTL": "USD_Alis",
    "TP_DK_EUR_A_YTL": "EUR_Alis",
    "TP_MK_F_BILESIK": "BIST100",
}


def fetch_evds(start, end):
    from evds import evdsAPI
    api_key = os.environ.get("EVDS_API_KEY")
    if not api_key:
        raise RuntimeError("EVDS_API_KEY ortam değişkeni bulunamadı (GitHub Secrets'a eklenmiş mi?).")

    evds = evdsAPI(api_key)
    df = evds.get_data(
        SERIES,
        startdate=start.strftime("%d-%m-%Y"),
        enddate=end.strftime("%d-%m-%Y"),
    )
    df = df.rename(columns=COLUMN_MAP)
    df["Tarih"] = pd.to_datetime(df["Tarih"], format="%d-%m-%Y", errors="coerce")
    df = df.dropna(subset=["Tarih"])
    return df[["Tarih", "USD_Alis", "EUR_Alis", "BIST100"]]


def main():
    if os.path.exists(DATA_PATH):
        hist = pd.read_parquet(DATA_PATH)
        hist["Tarih"] = pd.to_datetime(hist["Tarih"]).dt.normalize()
        last_date = hist["Tarih"].max()
    else:
        hist = pd.DataFrame(columns=["Tarih", "USD_Alis", "EUR_Alis", "BIST100"])
        last_date = pd.Timestamp(datetime.today().date()) - timedelta(days=365 * ILK_CALISTIRMA_YIL)

    start = last_date  # son günü de tekrar çek (TCMB bazen o günü sonradan düzeltiyor)
    end = pd.Timestamp(datetime.today().date())

    if start > end:
        print("Zaten güncel, yeni veri çekilmeyecek.")
        return

    try:
        new = fetch_evds(start, end)
    except Exception as e:
        print("EVDS verisi çekilemedi:", e)
        return

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
