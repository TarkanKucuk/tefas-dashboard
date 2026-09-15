"""
BİR KERELİK TEŞHİS — ALE'de bulduğumuz sorunun (sistemdeki veri, TEFAS'ın
gerçekte sahip olduğu veriden çok daha kısa başlıyor) BAŞKA hangi fonlarda da
olduğunu bulur. Hiçbir veriyi DEĞİŞTİRMEZ, sadece log'a yazdırır.

İKİ AŞAMALI çalışır:

1) HIZLI TARAMA (TEFAS'a hiç istek atmaz, saniyeler sürer):
   tefas_gecmis_veri.parquet'teki HER fonun "sistemdeki en eski tarihini"
   bulur. En eski tarihi YAKIN ZAMANLI (son SUPHELI_GUN_ESIGI gün içinde)
   olan fonları "şüpheli" işaretler. Bunlar YA gerçekten yeni kurulmuş
   fonlardır YA DA ALE gibi geçmişi eksik kalmış fonlardır — bu aşama
   ikisini ayırt etmez, sadece adayları daraltır.

2) DOĞRULAMA (TEFAS'a sorgu, SADECE şüpheli fonlar için):
   Her şüpheli fon için, sistemdeki en eski tarihten HEMEN ÖNCEKİ dar bir
   pencereyi (DOGRULAMA_PENCERE_GUN gün) TEFAS'a fund_code ile sorar.
   TEFAS o pencerede veri döndürürse, fon GERÇEKTEN eksik demektir (ALE ile
   aynı kök sorun). Döndürmezse, gerçekten yeni bir fondur — yanlış alarmdı.

Rate limit'e nazik davranmak için istekler arasında bekleme var; şüpheli
sayısı fazlaysa bu adım biraz uzun sürebilir (100 şüpheli ≈ 18-20 dakika).
"""
import pandas as pd
import time

DATA_PATH = "tefas_gecmis_veri.parquet"
SUPHELI_GUN_ESIGI = 365   # sistemdeki en eski tarih bugünden bu kadar gün içindeyse şüpheli say
DOGRULAMA_PENCERE_GUN = 45  # her şüpheli fon için, en eski tarihten öncesine doğru kaç gün sorgulayalım


def hizli_tarama():
    hist = pd.read_parquet(DATA_PATH)
    hist["Tarih"] = pd.to_datetime(hist["Tarih"])
    en_eski = hist.groupby("Fon Kodu")["Tarih"].min()

    esik_tarih = pd.Timestamp.today() - pd.Timedelta(days=SUPHELI_GUN_ESIGI)
    supheliler = en_eski[en_eski >= esik_tarih].sort_values(ascending=False)

    print(f"Toplam fon sayısı (sistemde): {len(en_eski)}")
    print(f"Sistemde en eski verisi son {SUPHELI_GUN_ESIGI} gün içinde başlayan "
          f"(şüpheli, ya yeni ya eksik) fon sayısı: {len(supheliler)}")
    print()
    for kod, tarih in supheliler.items():
        print(f"  {kod}: sistemde {tarih.date()} tarihinden itibaren veri var")
    return supheliler


def dogrulama(supheliler):
    from pytefas import Crawler
    tefas = Crawler()

    gercekten_eksik = []
    print()
    print("=" * 60)
    print(f"DOĞRULAMA (TEFAS'a sorgu) BAŞLIYOR — {len(supheliler)} fon kontrol edilecek...")
    print("=" * 60)

    # TEFAS'ın kendi "başlangıç tarihi 5 yıldan eski olamaz" kısıtına
    # takılmamak için güvenlik payıyla (4 yıl 11 ay) bir alt sınır koyuyoruz.
    min_izin_verilen = pd.Timestamp.today() - pd.DateOffset(years=4, months=11)

    for i, (kod, en_eski_tarih) in enumerate(supheliler.items()):
        pencere_bitis = en_eski_tarih - pd.Timedelta(days=1)
        pencere_baslangic = max(pencere_bitis - pd.Timedelta(days=DOGRULAMA_PENCERE_GUN), min_izin_verilen)

        if pencere_baslangic >= pencere_bitis:
            print(f"  [{i+1}/{len(supheliler)}] {kod}: zaten TEFAS'ın 5 yıllık sınırına yakın, atlanıyor.")
            continue

        try:
            df = tefas.fetch(
                start=pencere_baslangic.strftime("%Y-%m-%d"),
                end=pencere_bitis.strftime("%Y-%m-%d"),
                columns="info",
                kind="YAT",
                fund_code=kod,
            )
            if df is not None and not df.empty:
                gercek_en_eski = pd.to_datetime(df["date"]).min()
                print(f"  [{i+1}/{len(supheliler)}] {kod}: EKSİK! TEFAS'ta {gercek_en_eski.date()} "
                      f"tarihine kadar veri var (sistemde sadece {en_eski_tarih.date()}'den beri).")
                gercekten_eksik.append(kod)
            else:
                print(f"  [{i+1}/{len(supheliler)}] {kod}: doğrulandı — TEFAS'ta da bu tarihten öncesi yok, "
                      f"gerçekten yeni bir fon (yanlış alarm).")
        except Exception as e:
            print(f"  [{i+1}/{len(supheliler)}] {kod}: sorgu hatası ({e})")

        time.sleep(11)  # TEFAS rate limit: dakikada ~6 istek — nazik davranıyoruz

    print()
    print("=" * 60)
    print(f"SONUÇ: {len(gercekten_eksik)} fon GERÇEKTEN eksik geçmişe sahip (ALE ile aynı sorun):")
    print(", ".join(gercekten_eksik) if gercekten_eksik else "(hiç yok — sadece ALE'ymiş)")
    print("=" * 60)
    return gercekten_eksik


if __name__ == "__main__":
    supheliler = hizli_tarama()
    if len(supheliler) == 0:
        print("Şüpheli fon yok, doğrulama adımına gerek yok.")
    else:
        dogrulama(supheliler)
