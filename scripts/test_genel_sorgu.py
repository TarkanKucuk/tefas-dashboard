"""
HIZLI TEST — 17 Temmuz 2026'dan ÖNCEki dönemi, fund_code BELİRTMEDEN (yani
TEFAS'ın "tüm fonları listele" sorgusuyla) yeniden istersek, bilinen EKSİK
fonlar (ALE, YA1, YAR gibi) bu genel sorgunun içinde geliyor mu?

Cevap EVET ise: tek (ya da birkaç geniş) sorguyla TÜM eksik fonları birden
doldurabiliriz — her fonu tek tek fund_code ile sorgulamaya (1000+ istek,
saatler sürer) hiç gerek kalmaz.

Cevap HAYIR ise: TEFAS'ın genel sorgusu, o dönem için hâlâ bu fonları
göstermiyor demektir — bu durumda her fonu tek tek sorgulamak zorunda kalırız.

Bu script hiçbir dosyayı DEĞİŞTİRMEZ, sadece sonucu yazdırır.
"""
import pandas as pd
from pytefas import Crawler

# fonlar.txt'ten bilinen, gerçekten eksik olduğu doğrulanmış birkaç fon
TEST_FONLARI = ["ALE", "YA1", "YAR", "YBJ", "YBP"]


def main():
    tefas = Crawler()
    print("TEFAS'a GENEL (fund_code belirtilmeden) sorgu: 01.06.2026 - 16.07.2026...")
    df = tefas.fetch(
        start="2026-06-01",
        end="2026-07-16",
        columns="info",
        kind="YAT",
    )
    if df is None or df.empty:
        print("Genel sorgu hiç veri döndürmedi — beklenmedik, araştırılmalı.")
        return

    print(f"Genel sorgu {len(df)} satır, {df['fund_code'].nunique()} benzersiz fon döndürdü.")
    print()
    for kod in TEST_FONLARI:
        var_mi = kod in set(df["fund_code"])
        if var_mi:
            alt_df = df[df["fund_code"] == kod]
            print(f"  {kod}: VAR — {alt_df['date'].min()} - {alt_df['date'].max()} arası "
                  f"{len(alt_df)} satır bu genel sorguda geldi.")
        else:
            print(f"  {kod}: YOK — bu genel sorguda gelmedi.")

    bulunan = sum(1 for kod in TEST_FONLARI if kod in set(df["fund_code"]))
    print()
    print("=" * 60)
    if bulunan == len(TEST_FONLARI):
        print("SONUÇ: Tüm test fonları genel sorguda bulundu — tek/birkaç geniş "
              "sorguyla toplu düzeltme YAPILABİLİR görünüyor.")
    elif bulunan > 0:
        print(f"SONUÇ: {bulunan}/{len(TEST_FONLARI)} fon bulundu — KISMEN işe yarıyor, "
              "dikkatli değerlendirilmeli.")
    else:
        print("SONUÇ: Hiçbir test fonu genel sorguda bulunamadı — toplu düzeltme işe "
              "yaramaz, her fonu tek tek sorgulamamız gerekecek.")
    print("=" * 60)


if __name__ == "__main__":
    main()
