import pandas as pd
import os

print("--- tefas_acik_fonlar.parquet kontrolü ---")
if not os.path.exists("tefas_acik_fonlar.parquet"):
    print("DOSYA YOK!")
else:
    df = pd.read_parquet("tefas_acik_fonlar.parquet")
    print(f"Toplam açık fon sayısı: {len(df)}")
    print(f"Güncelleme tarihi: {df['Guncelleme_Tarihi'].iloc[0] if 'Guncelleme_Tarihi' in df.columns else '?'}")
    print(f"KSP bu listede var mı: {'EVET' if 'KSP' in df['Fon Kodu'].values else 'HAYIR'}")
    print(f"PHE bu listede var mı (kontrol amaçlı, olması lazım): {'EVET' if 'PHE' in df['Fon Kodu'].values else 'HAYIR'}")

print("\n--- tefas_gecmis_veri.parquet'te KSP'nin ilk işlem tarihi ---")
df2 = pd.read_parquet("tefas_gecmis_veri.parquet")
if "KSP" in df2["Fon Kodu"].unique():
    ilk_tarih = df2[df2["Fon Kodu"] == "KSP"]["Tarih"].min()
    print(f"KSP ilk tarih (bizim veride): {ilk_tarih}")
    son_tarih = df2["Tarih"].max()
    print(f"Genel son veri tarihi: {son_tarih}")
    print(f"KSP 'son 30 gün' filtresine giriyor mu: {(son_tarih - ilk_tarih).days <= 30}")
else:
    print("KSP tefas_gecmis_veri.parquet'te hiç yok.")
