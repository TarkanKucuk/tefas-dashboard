from tefasfon import get_funds
from datetime import datetime

def dump(baslik, **kwargs):
    print(f"\n--- {baslik} ---")
    try:
        df = get_funds(**kwargs)
        if df is None or df.empty:
            print("Sonuç boş.")
            return
        print(f"Satır sayısı: {len(df)}")
        print(f"TÜM KOLONLAR: {df.columns.tolist()}")
        ksp = df[df["fonKodu"] == "KSP"] if "fonKodu" in df.columns else df
        print("KSP satırı (varsa):")
        print(ksp.to_string())
    except Exception as e:
        print(f"HATA: {repr(e)}")

bugun = datetime.today().strftime("%d.%m.%Y")

# get_funds ile genel bilgi (fiyat/pay/yatırımcı sayısı vs.) çekelim,
# "Platform Durumu" gibi bir alan var mı diye tüm sütunlara bakacağız.
dump("get_funds - SEC - bugün, tüm fonlar", fund_type="SEC", start_date=bugun, end_date=bugun)
