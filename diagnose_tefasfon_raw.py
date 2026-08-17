from tefasfon import get_portfolio
from datetime import datetime

def test_tarih(baslik, tarih):
    print(f"\n--- {baslik} ({tarih}) ---")
    try:
        df = get_portfolio(fund_type="SEC", start_date=tarih, end_date=tarih)
        if df is None:
            print("Sonuç: None döndü")
            return
        print(f"Satır sayısı: {len(df)}")
        print(f"Kolonlar: {df.columns.tolist()}")
        if not df.empty:
            if 'fonKodu' in df.columns:
                pbr = df[df['fonKodu'] == 'PBR']
                print("PBR satırı:")
                print(pbr.to_string())
            else:
                print("İlk 3 satır:")
                print(df.head(3).to_string())
    except Exception as e:
        print(f"HATA: {repr(e)}")

bugun = datetime.today().strftime("%d.%m.%Y")
test_tarih("BUGÜN", bugun)
test_tarih("Sorunun başladığı civar (28 Temmuz 2026)", "28.07.2026")
test_tarih("Kesin çalıştığı bilinen eski tarih (01.06.2026)", "01.06.2026")
