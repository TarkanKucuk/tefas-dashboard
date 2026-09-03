"""
Fonlarca Skoru + Kategori Sıra No GEÇMİŞ ARŞİVİ.

Amaç: her iş günü için, o gün "bugünmüş" gibi kabul edilerek hesaplanmış
Kategori Skoru ve Sıra No değerlerini biriktirmek. Böylece ileride bir fonun
skorunun/sırasının zaman içinde nasıl değiştiği görülebilir.

Nasıl çalışır:
- Puanlama motoru (score_funds.build_fund_metrics) zaten anchor olarak verinin
  en son tarihini kullanıyor. Bu yüzden veriyi geçmiş bir güne (D) kadar kırpıp
  motoru çalıştırınca, tüm skorlar D günü itibarıyla hesaplanmış olur.
- Dosya HİÇ yoksa (ilk çalıştırma): son ~1 ayın her iş gününü geriye dönük
  hesaplayıp arşivi doldurur (backfill).
- Dosya varsa: sadece arşivde henüz olmayan (en yeni) günleri hesaplayıp ekler.

Önemli dürüstlük notları (yaklaşıklıklar):
- Açık/kapalı fon durumu: elimizde yalnızca GÜNCEL açık fon listesi var. Geçmiş
  günleri hesaplarken de bu güncel listeyi kullanıyoruz — yani "o gün açık mıydı"
  bilgisi tam doğru değil, bugünkü duruma göre yaklaşıktır.
- Risksiz oran (Sharpe için TLREF): score_funds içindeki tek güncel sabit
  kullanılır; geçmiş günler için de aynı sabit uygulanır (etkisi küçüktür).
"""
import os
import pandas as pd

import score_funds as sf

OUT_PATH = "skor_gecmisi.parquet"
BACKFILL_GUN = 30  # ilk çalıştırmada kaç takvim günü geriye gidilsin


def hesapla_bir_gun(df_tum, mapping, acik_fon_kodlari, hedef_tarih, bench_df=None):
    """Veriyi hedef_tarih'e kadar kırpıp o gün itibarıyla skor/sıra hesaplar.
    bench_df verilirse Sharpe risksiz oranı, o güne kadarki TLREF endeksinin son
    1 yıllık getirisiyle hesaplanır (aksi halde yedek sabit kullanılır)."""
    df_asof = df_tum[df_tum["Tarih"] <= hedef_tarih]
    if df_asof.empty:
        return None

    res, anchor = sf.build_fund_metrics(df_asof, bench_df)
    res = res.merge(mapping, on="Fon Kodu", how="left")
    res = res[res["Alt Kategori"].notna()]
    # Kapalı fonlar puanlamaya girmez (canlı sistemle birebir tutarlı).
    if acik_fon_kodlari is not None:
        res = res[res["Fon Kodu"].isin(acik_fon_kodlari)]
    if res.empty:
        return None
    res = sf.compute_scores(res)

    out = res[["Fon Kodu", "Alt Kategori", "TEFAS_Skoru", "Kategori_Sırası"]].copy()
    out = out[out["TEFAS_Skoru"].notna()]
    if out.empty:
        return None
    out = out.rename(columns={"TEFAS_Skoru": "Kategori Skoru", "Kategori_Sırası": "Sıra No"})
    out["Sıra No"] = out["Sıra No"].astype(int)
    out["Tarih"] = pd.Timestamp(hedef_tarih).normalize()
    return out[["Fon Kodu", "Tarih", "Alt Kategori", "Kategori Skoru", "Sıra No"]]


def main():
    df = pd.read_parquet(sf.DATA_PATH)
    df["Tarih"] = pd.to_datetime(df["Tarih"]).dt.normalize()
    df = df[df["Fiyat"] > 0].sort_values(["Fon Kodu", "Tarih"])

    mapping = pd.read_excel(sf.MAPPING_PATH)
    acik_fon_kodlari = sf.load_acik_fon_kodlari()

    # TLREF endeksi (Sharpe risksiz oranı için). Her geçmiş gün, o güne kadarki
    # kendi son 1 yıllık TLREF getirisiyle hesaplanır. Yoksa yedek sabite düşülür.
    bench_df = None
    if os.path.exists(sf.BENCHMARK_PATH):
        bench_df = pd.read_parquet(sf.BENCHMARK_PATH)
        bench_df["Tarih"] = pd.to_datetime(bench_df["Tarih"]).dt.normalize()
        bench_df = bench_df.sort_values("Tarih").reset_index(drop=True)

    # Veride gerçekten var olan işlem günleri (TEFAS zaten sadece iş günü yayınlar)
    tum_tarihler = sorted(df["Tarih"].unique())
    if not tum_tarihler:
        print("Veri yok, çıkılıyor.")
        return
    son_tarih = tum_tarihler[-1]

    if os.path.exists(OUT_PATH):
        mevcut = pd.read_parquet(OUT_PATH)
        mevcut["Tarih"] = pd.to_datetime(mevcut["Tarih"]).dt.normalize()
        # Sadece arşivdeki EN SON günden daha yeni günleri hesapla (ileriye doğru).
        # "Arşivde olmayan tüm günler" DEĞİL — çünkü backfill penceresinden (son 1 ay)
        # önceki eski günler kasıtlı olarak arşivde yok; onları geriye dönük yeniden
        # hesaplamaya çalışmak hem gereksiz hem de o kadar eski tarihlerde yeterli
        # geçmiş olmadığı için hataya yol açar. Aradan gün atlanmışsa (workflow
        # çalışmamışsa) bu mantık o boşluğu da ileri doğru doldurur.
        son_arsiv = mevcut["Tarih"].max()
        hedef_tarihler = [t for t in tum_tarihler if t > son_arsiv]
        print(f"Arşiv mevcut ({len(mevcut)} satır, son gün {pd.Timestamp(son_arsiv).date()}). "
              f"Eklenecek yeni gün sayısı: {len(hedef_tarihler)}")
    else:
        mevcut = pd.DataFrame(columns=["Fon Kodu", "Tarih", "Alt Kategori", "Kategori Skoru", "Sıra No"])
        baslangic = pd.Timestamp(son_tarih).normalize() - pd.Timedelta(days=BACKFILL_GUN)
        hedef_tarihler = [t for t in tum_tarihler if t >= baslangic]
        print(f"İlk çalıştırma — son {BACKFILL_GUN} günün {len(hedef_tarihler)} iş günü "
              f"geriye dönük hesaplanacak (backfill).")

    if not hedef_tarihler:
        print("Hesaplanacak yeni gün yok — arşiv güncel.")
        return

    yeni_parcalar = []
    for t in hedef_tarihler:
        gun_sonuc = hesapla_bir_gun(df, mapping, acik_fon_kodlari, t, bench_df)
        if gun_sonuc is not None:
            yeni_parcalar.append(gun_sonuc)
            print(f"  {pd.Timestamp(t).date()}: {len(gun_sonuc)} fon puanlandı.")
        else:
            print(f"  {pd.Timestamp(t).date()}: puanlanacak fon bulunamadı, atlandı.")

    if not yeni_parcalar:
        print("Hiç yeni kayıt üretilmedi.")
        if mevcut.empty:
            return
        birlesik = mevcut
    else:
        birlesik = pd.concat([mevcut] + yeni_parcalar, ignore_index=True)

    birlesik = birlesik.drop_duplicates(subset=["Fon Kodu", "Tarih"], keep="last")
    birlesik = birlesik.sort_values(["Tarih", "Alt Kategori", "Sıra No"]).reset_index(drop=True)
    birlesik.to_parquet(OUT_PATH, index=False)
    print(f"✅ Arşiv kaydedildi: {len(birlesik)} satır, "
          f"{birlesik['Tarih'].nunique()} farklı gün, "
          f"{birlesik['Fon Kodu'].nunique()} farklı fon -> {OUT_PATH}")


if __name__ == "__main__":
    main()
