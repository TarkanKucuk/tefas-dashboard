import pandas as pd
import os

KOD = "KSP"

print(f"--- {KOD} için veri kaynağı kontrolü ---\n")

# 1) Ana fiyat verisi
try:
    df = pd.read_parquet("tefas_gecmis_veri.parquet")
    var = KOD in df["Fon Kodu"].unique()
    print(f"tefas_gecmis_veri.parquet: {'VAR' if var else 'YOK'}")
except Exception as e:
    print("tefas_gecmis_veri.parquet okunamadı:", e)

# 2) Eşleştirme dosyası
try:
    mapping = pd.read_excel("fon_kategori_eslestirme.xlsx")
    var = KOD in mapping["Fon Kodu"].unique()
    print(f"fon_kategori_eslestirme.xlsx: {'VAR' if var else 'YOK'}")
except Exception as e:
    print("fon_kategori_eslestirme.xlsx okunamadı:", e)

# 3) Varlık dağılımı (Fon Unvanı kaynağı)
try:
    alloc = pd.read_parquet("tefas_portfoy_dagilim.parquet")
    var = KOD in alloc["Fon Kodu"].unique()
    print(f"tefas_portfoy_dagilim.parquet: {'VAR' if var else 'YOK'}")
    if var:
        row = alloc[alloc["Fon Kodu"] == KOD].sort_values("Tarih").iloc[-1]
        print(f"  Fon Unvanı: {row.get('Fon Unvanı')}")
except Exception as e:
    print("tefas_portfoy_dagilim.parquet okunamadı:", e)

# 4) Fon bilgileri (risk/stopaj/ücret kaynağı)
try:
    fb = pd.read_parquet("fon_bilgileri.parquet")
    var = KOD in fb["Fon Kodu"].unique()
    print(f"fon_bilgileri.parquet: {'VAR' if var else 'YOK'}")
except Exception as e:
    print("fon_bilgileri.parquet okunamadı:", e)
