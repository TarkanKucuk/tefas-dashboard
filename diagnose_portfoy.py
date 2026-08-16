import pandas as pd

df = pd.read_parquet("tefas_portfoy_dagilim.parquet")
df["Tarih"] = pd.to_datetime(df["Tarih"]).dt.normalize()
df = df.sort_values("Tarih")

print(f"Toplam satır: {len(df)}")
print(f"Tarih aralığı: {df['Tarih'].min().date()} -> {df['Tarih'].max().date()}")

exclude = {"Fon Kodu", "Tarih", "Fon Unvanı"}
cat_cols = [c for c in df.columns if c not in exclude]

# Genel olarak (tüm fonlar): her tarih için kategorilerden en az biri dolu mu?
by_date = df.groupby("Tarih")[cat_cols].apply(lambda g: g.notna().any().any())
valid_dates = by_date[by_date].index
print(f"\nGenelde (tüm fonlar) veri içeren en son tarih: {valid_dates.max().date() if len(valid_dates) else 'YOK'}")
print(f"Son 10 tarih ve o günün 'en az bir fonda dolu veri var mı' durumu:")
print(by_date.tail(10).to_string())

# Örnek fon: PBR
print("\n--- PBR örneği ---")
pbr = df[df["Fon Kodu"] == "PBR"].sort_values("Tarih")
print(f"PBR toplam satır: {len(pbr)}")
print(f"PBR tarih aralığı: {pbr['Tarih'].min().date()} -> {pbr['Tarih'].max().date()}")
pbr_filled = pbr[pbr[cat_cols].notna().any(axis=1)]
print(f"PBR en son DOLU satır tarihi: {pbr_filled['Tarih'].max().date() if not pbr_filled.empty else 'HİÇ DOLU SATIR YOK'}")
print("\nPBR son 10 satır (ilk 5 kategori kolonu):")
print(pbr[["Tarih"] + cat_cols[:5]].tail(10).to_string())
