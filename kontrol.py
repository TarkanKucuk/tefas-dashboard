import pandas as pd

print("\n===== tefas_portfoy_dagilim.parquet =====")
df = pd.read_parquet("tefas_portfoy_dagilim.parquet")
print("Kolonlar:", df.columns.tolist())
print("\nİlk 3 satır:")
print(df.head(3))

print("\n===== fon_kategori_eslestirme.xlsx =====")
df2 = pd.read_excel("fon_kategori_eslestirme.xlsx")
print("Kolonlar:", df2.columns.tolist())
print("\nİlk 3 satır:")
print(df2.head(3))
