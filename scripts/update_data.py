import pandas as pd
from pytefas import Crawler
from datetime import datetime, timedelta

DATA_PATH = "tefas_gecmis_veri.parquet"


def main():
    hist = pd.read_parquet(DATA_PATH)
    hist['Tarih'] = pd.to_datetime(hist['Tarih']).dt.normalize()  # saat bileşenini at, sadece tarih kalsın
    last_date = hist['Tarih'].max()

    # Son tarihi de dahil ederek tekrar çekiyoruz: TEFAS bazen aynı günün verisini
    # gün içinde günceller/düzeltir, en taze halini almak istiyoruz.
    start = last_date
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
    df['Tarih'] = pd.to_datetime(df['Tarih']).dt.normalize()

    yeni_son_tarih = df['Tarih'].max()

    # Veritabanındaki last_date VE sonrasına ait ne varsa çıkar (mükerrer/eskimiş kayıt bırakmamak için),
    # yeni çekilen veriyle değiştir. Böylece "aynı tarih iki kez" ya da "eski/güncellenmemiş satır" kalmaz.
    hist_temiz = hist[hist['Tarih'] < start]

    combined = pd.concat([hist_temiz, df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['Fon Kodu', 'Tarih'], keep='last')
    combined = combined.sort_values(['Fon Kodu', 'Tarih'])
    combined.to_parquet(DATA_PATH, index=False)

    yeni_gun_sayisi = df['Tarih'].nunique()
    print(f"{start.date()} - {yeni_son_tarih.date()} arası yeniden çekildi "
          f"({yeni_gun_sayisi} gün, {len(df)} satır). Toplam satır: {len(combined)}")


if __name__ == "__main__":
    main()
