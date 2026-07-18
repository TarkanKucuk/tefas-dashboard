import pandas as pd
from pytefas import Crawler
from datetime import datetime, timedelta

DATA_PATH = "tefas_gecmis_veri.parquet"


def main():
    hist = pd.read_parquet(DATA_PATH)
    hist['Tarih'] = pd.to_datetime(hist['Tarih'])
    last_date = hist['Tarih'].max()
    start = last_date + timedelta(days=1)
    end = datetime.today()

    if start.date() > end.date():
        print("Zaten güncel, yeni veri çekilmeyecek.")
        return

    tefas = Crawler()
    df = tefas.fetch(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        columns="info",
        kind="YAT",
    )

    if df.empty:
        print("Bu tarih aralığında yeni veri yok (tatil/hafta sonu olabilir).")
        return

    df = df.rename(columns={
        'date': 'Tarih',
        'fund_code': 'Fon Kodu',
        'price': 'Fiyat',
        'shares_outstanding': 'Tedavüldeki Pay Sayısı',
        'investor_count': 'Kişi Sayısı',
        'portfolio_size': 'Fon Toplam Değer',
    })
    df = df[['Fon Kodu', 'Tarih', 'Fiyat', 'Tedavüldeki Pay Sayısı',
              'Fon Toplam Değer', 'Kişi Sayısı']]
    df['Tarih'] = pd.to_datetime(df['Tarih'])

    combined = pd.concat([hist, df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['Fon Kodu', 'Tarih'], keep='last')
    combined = combined.sort_values(['Fon Kodu', 'Tarih'])
    combined.to_parquet(DATA_PATH, index=False)
    print(f"{len(df)} yeni satır eklendi. Toplam satır: {len(combined)}")


if __name__ == "__main__":
    main()
