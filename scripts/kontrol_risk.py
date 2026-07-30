import pandas as pd

print("=" * 60)
print("1️⃣  BORSAPY KONTROLÜ")
print("=" * 60)

try:
    import borsapy as bp
    print("✅ borsapy kurulu")
    
    # Fonksiyonları listele
    funcs = [x for x in dir(bp) if not x.startswith('_')]
    print(f"\nMevcut fonksiyonlar ({len(funcs)} adet):")
    for f in funcs:
        print(f"  - {f}")
    
    # fund_info veya funds varsa dene
    for func_name in ['fund_info', 'funds', 'get_funds', 'fund_details']:
        if hasattr(bp, func_name):
            print(f"\n👉 '{func_name}()' çağrılıyor...")
            try:
                df = getattr(bp, func_name)()
                if isinstance(df, pd.DataFrame):
                    print(f"   ✅ Başarılı! Kolonlar: {df.columns.tolist()}")
                    # Risk içeren kolonları bul
                    risk_cols = [c for c in df.columns if 'risk' in c.lower()]
                    if risk_cols:
                        print(f"   🎯 RİSK KOLONLARI BULUNDU: {risk_cols}")
                    else:
                        print("   ⚠️ Risk içeren kolon bulunamadı")
                else:
                    print(f"   ⚠️ DataFrame değil, tip: {type(df)}")
            except Exception as e:
                print(f"   ❌ Hata: {e}")
    
    # management_fees varsa dene
    if hasattr(bp, 'management_fees'):
        print("\n👉 'management_fees()' çağrılıyor...")
        try:
            df = bp.management_fees()
            print(f"   ✅ Başarılı! Kolonlar: {df.columns.tolist()}")
            risk_cols = [c for c in df.columns if 'risk' in c.lower()]
            if risk_cols:
                print(f"   🎯 RİSK KOLONLARI BULUNDU: {risk_cols}")
            else:
                print("   ⚠️ Risk içeren kolon bulunamadı")
        except Exception as e:
            print(f"   ❌ Hata: {e}")

except ImportError:
    print("❌ borsapy kurulu değil")

print("\n" + "=" * 60)
print("2️⃣  TEFASFON KONTROLÜ")
print("=" * 60)

try:
    import tefasfon
    print("✅ tefasfon kurulu")
    
    funcs = [x for x in dir(tefasfon) if not x.startswith('_')]
    print(f"\nMevcut fonksiyonlar ({len(funcs)} adet):")
    for f in funcs:
        print(f"  - {f}")
    
    # get_portfolio dışında başka fonksiyon var mı?
    for func_name in ['get_fund_info', 'get_fund_details', 'get_funds', 'get_fund']:
        if hasattr(tefasfon, func_name):
            print(f"\n👉 '{func_name}()' çağrılıyor...")
            try:
                result = getattr(tefasfon, func_name)()
                print(f"   ✅ Başarılı! Tip: {type(result)}")
                if isinstance(result, pd.DataFrame):
                    print(f"   Kolonlar: {result.columns.tolist()}")
            except Exception as e:
                print(f"   ❌ Hata: {e}")

except ImportError:
    print("❌ tefasfon kurulu değil")

print("\n" + "=" * 60)
print("3️⃣  FON_KATEGORI_ESLESTIRME.XLSX KONTROLÜ")
print("=" * 60)

try:
    df = pd.read_excel("fon_kategori_eslestirme.xlsx")
    print(f"✅ Dosya okundu. Kolonlar: {df.columns.tolist()}")
    risk_cols = [c for c in df.columns if 'risk' in c.lower()]
    if risk_cols:
        print(f"🎯 RİSK KOLONLARI BULUNDU: {risk_cols}")
    else:
        print("⚠️ Risk içeren kolon bulunamadı")
except Exception as e:
    print(f"❌ Dosya okunamadı: {e}")

print("\n" + "=" * 60)
print("KONTROL TAMAMLANDI")
print("=" * 60)
