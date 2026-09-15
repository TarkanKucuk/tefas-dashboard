"""
BİR KERELİK TEŞHİS — ALE (AK PORTFÖY PARA PİYASASI TL FONU) neden eksik veri
gösteriyor?

Bu script hiçbir dosyayı DEĞİŞTİRMEZ, sadece GitHub Actions loglarına bilgi
yazdırır. Amaç iki soruyu kesin olarak yanıtlamak:

1. Fiyat geçmişi: TEFAS'ın kendisi ALE için 17 Temmuz 2026'dan daha eski veri
   veriyor mu (bu durumda bizim script'imizde bir hata var demektir), yoksa
   TEFAS'ın kendisi de o tarihten öncesini vermiyor mu (bu durumda veri
   kaynağının kendi sınırlaması, bizim çözebileceğimiz bir şey değil)?
2. Risk değeri: ALE, TEFAS'ın risk-değeri sorgusunun taradığı 5 fon tipinden
   (SEC/PEN/ETF/RE/VC) herhangi birinde hiç geçiyor mu?

KULLANIM: GitHub Actions'ta bir kez çalıştır, "Portfoy dagilim verisini
guncelle" gibi bir adım olarak EKLEMEDEN, sadece bu script'i tek başına
manuel bir workflow ile çalıştır ve logu paylaş.
"""
import pandas as pd

FON_KODU = "ALE"


def fiyat_gecmisi_testi():
    print("=" * 60)
    print("1) FİYAT GEÇMİŞİ TESTİ")
    print("=" * 60)

    # Mevcut parquet'te ALE'nin en eski/en yeni tarihi ne?
    try:
        hist = pd.read_parquet("tefas_gecmis_veri.parquet")
        hist["Tarih"] = pd.to_datetime(hist["Tarih"])
        ale_hist = hist[hist["Fon Kodu"] == FON_KODU]
        if ale_hist.empty:
            print(f"  Mevcut parquet'te {FON_KODU} için hiç kayıt yok.")
        else:
            print(f"  Mevcut parquet'te {FON_KODU}: "
                  f"{ale_hist['Tarih'].min().date()} - {ale_hist['Tarih'].max().date()} "
                  f"({len(ale_hist)} satır)")
    except Exception as e:
        print(f"  tefas_gecmis_veri.parquet okunamadı: {e}")

    # TEFAS'ın kendisine, GENİŞ bir tarih aralığıyla, SADECE ALE için sorup,
    # gerçekten ne kadar eskiye gittiğini görelim.
    try:
        from pytefas import Crawler
        tefas = Crawler()
        print(f"\n  TEFAS'a doğrudan soruluyor: {FON_KODU}, 01.01.2010 - bugün...")
        df = tefas.fetch(
            start="2010-01-01",
            end=pd.Timestamp.today().strftime("%Y-%m-%d"),
            columns="info",
            kind="YAT",
            fund_code=FON_KODU,
        )
        if df is None or df.empty:
            print(f"  TEFAS API'si {FON_KODU} için (fon_kodu filtresiyle) hiç veri döndürmedi.")
        else:
            print(f"  TEFAS API'sinden dönen: {df['date'].min()} - {df['date'].max()} ({len(df)} satır)")
            print("  İlk 3 satır:")
            print(df.head(3).to_string())
    except TypeError as e:
        # fetch() 'fon_kodu' parametresini desteklemiyor olabilir — filtresiz dene
        print(f"  (fon_kodu parametresiyle çağrı desteklenmiyor olabilir: {e})")
        print("  Filtresiz (tüm fonlar) deneniyor, sonra ALE'ye bakılacak...")
        try:
            from pytefas import Crawler
            tefas = Crawler()
            df = tefas.fetch(start="2010-01-01", end="2010-06-01", columns="info", kind="YAT")
            print(f"  Örnek çağrı başarılı, {len(df)} satır döndü (fon_kodu filtresi test edilemedi).")
        except Exception as e2:
            print(f"  Filtresiz deneme de başarısız: {e2}")
    except Exception as e:
        print(f"  TEFAS'a doğrudan soru başarısız: {e}")


def risk_degeri_testi():
    print()
    print("=" * 60)
    print("2) RİSK DEĞERİ TESTİ")
    print("=" * 60)

    try:
        fb = pd.read_parquet("fon_bilgileri.parquet")
        row = fb[fb["Fon Kodu"] == FON_KODU]
        if row.empty:
            print(f"  fon_bilgileri.parquet'te {FON_KODU} için hiç satır yok.")
        else:
            print(f"  fon_bilgileri.parquet'teki {FON_KODU} satırı:")
            print(row.to_string())
    except Exception as e:
        print(f"  fon_bilgileri.parquet okunamadı: {e}")

    try:
        from tefasfon import get_returns
        for ft in ["SEC", "PEN", "ETF", "RE", "VC"]:
            try:
                df = get_returns(fund_type=ft, basis="RB")
                if df is None or df.empty:
                    print(f"  {ft}: boş sonuç döndü.")
                    continue
                if "fonKodu" not in df.columns:
                    print(f"  {ft}: 'fonKodu' kolonu yok, kolonlar: {list(df.columns)}")
                    continue
                var_mi = FON_KODU in set(df["fonKodu"])
                print(f"  {ft}: {len(df)} fon döndü, {FON_KODU} içinde mi? {'EVET' if var_mi else 'hayır'}")
                if var_mi:
                    print("   ", df[df["fonKodu"] == FON_KODU].to_string())
            except Exception as e:
                print(f"  {ft}: hata ({e})")
    except Exception as e:
        print(f"  tefasfon.get_returns import edilemedi: {e}")


if __name__ == "__main__":
    fiyat_gecmisi_testi()
    risk_degeri_testi()
