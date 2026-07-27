import pandas as pd
from datetime import date

DATA_PATH = "fon_bilgileri.parquet"
MAPPING_PATH = "fon_kategori_eslestirme.xlsx"


def main():
    from borsapy.tax import classify_fund_tax_category, get_withholding_tax_rate
    import borsapy as bp

    mapping = pd.read_excel(MAPPING_PATH)

    kayitlar = []
    for _, r in mapping.iterrows():
        kod = r["Fon Kodu"]
        semsiye = r.get("Şemsiye Fon Türü", "") or ""
        ad = r.get("Fon Adı", "") or ""

        tax_cat = classify_fund_tax_category(semsiye, ad)
        stopaj = get_withholding_tax_rate(tax_cat, date.today(), None) if tax_cat else None

        kayitlar.append({
            "Fon Kodu": kod,
            "Vergi_Kategorisi": tax_cat,
            "Stopaj_Orani": stopaj,
        })

    stopaj_df = pd.DataFrame(kayitlar)

    try:
        fees_df = bp.management_fees()
        fees_df = fees_df.rename(columns={
            "fund_code": "Fon Kodu",
            "applied_fee": "Uygulanan_Yonetim_Ucreti_%",
            "prospectus_fee": "Izahname_Yonetim_Ucreti_%",
            "max_expense_ratio": "Maks_Toplam_Gider_Orani_%",
            "annual_return": "Yillik_Getiri_borsapy_%",
        })
        fees_df = fees_df[["Fon Kodu", "Uygulanan_Yonetim_Ucreti_%", "Izahname_Yonetim_Ucreti_%",
                            "Maks_Toplam_Gider_Orani_%", "Yillik_Getiri_borsapy_%"]]
    except Exception as e:
        print("Yönetim ücreti verisi çekilemedi:", e)
        fees_df = pd.DataFrame(columns=["Fon Kodu", "Uygulanan_Yonetim_Ucreti_%", "Izahname_Yonetim_Ucreti_%",
                                         "Maks_Toplam_Gider_Orani_%", "Yillik_Getiri_borsapy_%"])

    combined = stopaj_df.merge(fees_df, on="Fon Kodu", how="left")
    combined.to_parquet(DATA_PATH, index=False)
    print(f"fon_bilgileri.parquet güncellendi. {len(combined)} fon işlendi, "
          f"{combined['Uygulanan_Yonetim_Ucreti_%'].notna().sum()} fon için yönetim ücreti bulundu.")


if __name__ == "__main__":
    main()
