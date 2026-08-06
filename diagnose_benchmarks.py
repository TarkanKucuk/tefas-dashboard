import pandas as pd

df = pd.read_parquet("benchmarklar.parquet")
df["Tarih"] = pd.to_datetime(df["Tarih"]).dt.normalize()
df = df.sort_values("Tarih")

print(f"Toplam satır: {len(df)}")
print(f"Tarih aralığı: {df['Tarih'].min().date()} -> {df['Tarih'].max().date()}")
print()

for col in ["USD_Alis", "EUR_Alis", "BIST100", "TLREF_Endeks", "Altin_Gram"]:
    if col not in df.columns:
        print(f"{col}: KOLON HİÇ YOK")
        continue
    valid = df[df[col].notna()]
    n = len(valid)
    if n == 0:
        print(f"{col}: TÜM SATIRLAR BOŞ (0/{len(df)})")
    else:
        print(f"{col}: {n}/{len(df)} dolu | dolu tarih aralığı: {valid['Tarih'].min().date()} -> {valid['Tarih'].max().date()}")

print()
print("Son 15 satır (tüm kolonlar):")
print(df.tail(15).to_string())
