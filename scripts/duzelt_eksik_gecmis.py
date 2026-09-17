"""
BİR KERELİK TOPLU DÜZELTME — 17 Temmuz 2026'da (TEFAS'ın kendi "tüm fonları
listele" sorgusunun kapsamı genişlediği için) sisteme "yeni" gibi görünüp
geçmişleri hiç çekilmemiş ~1140 fonun (ALE dahil) eksik geçmişini doldurur.

YÖNTEM: Her fonu tek tek fund_code ile sorgulamak yerine (1000+ istek, 2+
saat sürüyordu ve bitmiyordu), GENEL (fund_code belirtilmeden) sorgular
kullanır — test_genel_sorgu.py ile doğrulandı: TEFAS'ın genel "tüm fonları
listele" sorgusu, bu fonları GEÇMİŞE DÖNÜK olarak da (17 Temmuz'dan öncesi
için bile) doğru şekilde döndürüyor. Bu yüzden sadece BİRKAÇ geniş (ama çok
büyük olmayan, 3 aylık dilimlere bölünmüş) sorgu yeterli.

Tarih aralığı: TEFAS'ın kendi API'sinin "başlangıç tarihi 5 yıldan eski
olamaz" kısıtına güvenlik payıyla uymak için, bugünden ~4 yıl 10 ay
öncesinden, 16 Temmuz 2026'ya (17 Temmuz'dan itibaren zaten verimiz var)
kadar, 3 aylık dilimler halinde çekilir.

update_data.py'ye HİÇ dokunmaz; sadece ondan kolon eşleme mantığını ödünç
alır, böylece üretilen veri günlük pipeline ile birebir aynı biçimde olur.
"""
import pandas as pd
from pytefas import Crawler
import time

DATA_PATH = "tefas_gecmis_veri.parquet"
BITIS_TARIHI = pd.Timestamp("2026-07-16")  # 17 Temmuz'dan itibaren zaten veri var


def parca_tarihleri_olustur():
    """Başlangıçtan (5 yıl sınırı, güvenlik payıyla) bitişe, 3 aylık dilimler."""
    baslangic = pd.Timestamp.today().normalize() - pd.DateOffset(years=4, months=10)
    parcalar = []
    t = baslangic
    while t < BITIS_TARIHI:
        parca_bitis = min(t + pd.DateOffset(months=3), BITIS_TARIHI)
        parcalar.append((t, parca_bitis))
        t = parca_bitis + pd.Timedelta(days=1)
    return parcalar


def main():
    hist = pd.read_parquet(DATA_PATH)
    hist["Tarih"] = pd.to_datetime(hist["Tarih"]).dt.normalize()
    print(f"Mevcut veri: {len(hist)} satır.")

    tefas = Crawler()
    parcalar = parca_tarihleri_olustur()
    print(f"{len(parcalar)} parça halinde, {parcalar[0][0].date()} - {parcalar[-1][1].date()} arası çekilecek.")

    tum_df_listesi = []
    for i, (bas, bit) in enumerate(parcalar):
        print(f"  [{i+1}/{len(parcalar)}] {bas.date()} - {bit.date()} çekiliyor...")
        try:
            df = tefas.fetch(
                start=bas.strftime("%Y-%m-%d"),
                end=bit.strftime("%Y-%m-%d"),
                columns="info",
                kind="YAT",
            )
            if df is not None and not df.empty:
                print(f"    {len(df)} satır, {df['fund_code'].nunique()} fon geldi.")
                tum_df_listesi.append(df)
            else:
                print("    Boş döndü.")
        except Exception as e:
            print(f"    HATA: {e}")
        time.sleep(11)  # TEFAS rate limit: dakikada ~6 istek — nazik davranıyoruz

    if not tum_df_listesi:
        print("Hiç veri çekilemedi, dosya değiştirilmedi.")
        return

    yeni = pd.concat(tum_df_listesi, ignore_index=True)
    yeni = yeni.rename(columns={
        "date": "Tarih",
        "fund_code": "Fon Kodu",
        "price": "Fiyat",
        "shares_outstanding": "Tedavüldeki Pay Sayısı",
        "investor_count": "Kişi Sayısı",
        "portfolio_size": "Fon Toplam Değer",
    })
    yeni = yeni[["Fon Kodu", "Tarih", "Fiyat", "Tedavüldeki Pay Sayısı",
                 "Fon Toplam Değer", "Kişi Sayısı"]]
    yeni["Tarih"] = pd.to_datetime(yeni["Tarih"]).dt.normalize()

    # Aynı Fon Kodu+Tarih için mevcutla çakışma olursa (beklenmez, farklı
    # dönemler), yeni çekilen (taze) veriyi tercih ediyoruz — mevcut 17
    # Temmuz-sonrası veriye hiç dokunmuyor, sadece öncesini dolduruyoruz.
    onceki_toplam = len(hist)
    combined = pd.concat([hist, yeni], ignore_index=True)
    combined = combined.drop_duplicates(subset=["Fon Kodu", "Tarih"], keep="last")
    combined = combined.sort_values(["Fon Kodu", "Tarih"])
    combined.to_parquet(DATA_PATH, index=False)

    print(f"✅ Düzeltme tamam. {len(yeni)} satır çekildi, {len(combined) - onceki_toplam} yeni satır eklendi. "
          f"Toplam: {len(combined)} satır.")


if __name__ == "__main__":
    main()
