"""
scripts/export_fon_kartlari.py

Her fon için tek bir JSON dosyası üretir (docs/data/fon-kartlari/{KOD}.json).
Bu JSON'lar fon kartı sayfasının (fon_karti.html / gelecekte fon-karti.html şablonu)
mock verisini gerçek veriyle değiştirmek için kullanılır.

Kaynaklar:
  - tefas_gecmis_veri.parquet   (Tarih, Fon Kodu, Fiyat, Kişi Sayısı, Fon Toplam Değer,
                                  Tedavüldeki Pay Sayısı)  -> score_funds.py ile aynı kaynak
  - fon_kategori_eslestirme.xlsx (Fon Kodu, Fon Adı, Şemsiye Fon Türü, Alt Kategori)
  - fon_bilgileri.parquet       (Fon Kodu, Risk_Degeri, Stopaj_Orani,
                                  Uygulanan_Yonetim_Ucreti_%, ...)
  - tefas_portfoy_dagilim.parquet (Fon Kodu, Tarih, + ~44 varlık kategorisi kolonu)
  - benchmarklar.parquet        (Tarih, USD_Alis, EUR_Alis, BIST100, TLREF_Endeks, Altin_Gram)

Varsayımlar / DOĞRULA:
  * tefas_portfoy_dagilim.parquet içinde "Fon Kodu" ve "Tarih" dışındaki TÜM kolonlar
    varlık kategorisi (%) kabul ediliyor. Farklıysa ALLOC_EXCLUDE_COLS'a ekle.
  * fon_kategori_eslestirme.xlsx içindeki kolon adları: "Fon Kodu", "Fon Adı",
    "Şemsiye Fon Türü", "Alt Kategori". Gerçek adlar farklıysa aşağıdaki
    MAPPING_COLS sözlüğünü güncelle.
  * Fonlarca Skoru + alt skorlar score_funds.py'deki build_fund_metrics/compute_scores
    fonksiyonlarından import edilir (aynı klasörde olmaları gerekir).
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_funds import build_fund_metrics, compute_scores  # noqa: E402

# ---------------------------------------------------------------------------
# Yol tanımları
# ---------------------------------------------------------------------------
PRICE_PATH = "tefas_gecmis_veri.parquet"
MAPPING_PATH = "fon_kategori_eslestirme.xlsx"
FON_BILGI_PATH = "fon_bilgileri.parquet"
ALLOC_PATH = "tefas_portfoy_dagilim.parquet"
BENCHMARK_PATH = "benchmarklar.parquet"
OUT_DIR = "docs/data/fon-kartlari"

MAPPING_COLS = {
    "kod": "Fon Kodu",
    "ad": "Fon Adı",
    "semsiye": "Şemsiye Fon Türü",
    "kategori": "Alt Kategori",
}

ALLOC_EXCLUDE_COLS = {"Fon Kodu", "Tarih", "Fon Unvanı"}

# Dönem sekmeleri: (anahtar, gün sayısı ya da None=yılbaşı)
PERIODS = [
    ("1H", 7), ("1A", 30), ("3A", 90), ("6A", 180),
    ("YB", None), ("1Y", 365), ("3Y", 365 * 3), ("5Y", 365 * 5),
]

BENCHMARK_COLS = {
    "USD": "USD_Alis", "EUR": "EUR_Alis", "BIST100": "BIST100",
    "TLREF": "TLREF_Endeks", "Altin": "Altin_Gram",
}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def period_return(series_dates, series_values, anchor_date, days=None):
    """anchor_date'ten `days` gün öncesine (ya da yılbaşına) göre % getiri hesaplar.
    Serinin kendi son DOLU değerini kullanır — örn. TLREF birkaç gün gecikmeli
    yayınlanıyorsa, sadece o serinin kendi son dolu tarihine göre hesaplanır;
    diğer serileri veya dönemleri etkilemez."""
    valid = series_values.notna()
    dates_valid = series_dates[valid]
    values_valid = series_values[valid]
    if values_valid.empty:
        return None
    latest_val = values_valid.iloc[-1]

    if days is None:
        cutoff = pd.Timestamp(year=anchor_date.year, month=1, day=1)
    else:
        cutoff = anchor_date - pd.Timedelta(days=days)
    past = values_valid[dates_valid <= cutoff]
    if past.empty:
        return None
    past_val = past.iloc[-1]
    if past_val == 0:
        return None
    return round(float((latest_val / past_val - 1) * 100), 2)


def build_returns_table(fund_prices):
    """Günlük/Haftalık/Aylık/3A/6A/Yılbaşı/1Y/3Y getiri tablosu."""
    dates = fund_prices["Tarih"]
    prices = fund_prices["Fiyat"]
    anchor = dates.max()

    gunluk = None
    if len(prices) >= 2:
        prev, last = prices.iloc[-2], prices.iloc[-1]
        if prev and not pd.isna(prev):
            gunluk = round(float((last / prev - 1) * 100), 2)

    return {
        "Günlük": gunluk,
        "Haftalık": period_return(dates, prices, anchor, 7),
        "Aylık": period_return(dates, prices, anchor, 30),
        "3 Ay": period_return(dates, prices, anchor, 90),
        "6 Ay": period_return(dates, prices, anchor, 180),
        "Yılbaşı": period_return(dates, prices, anchor, None),
        "1 Yıl": period_return(dates, prices, anchor, 365),
        "3 Yıl": period_return(dates, prices, anchor, 365 * 3),
    }


def build_compare_table(fund_prices, bench_df):
    """Her dönem sekmesi için PBR + her benchmark'ın % getirisi."""
    dates = fund_prices["Tarih"]
    prices = fund_prices["Fiyat"]
    anchor = dates.max()

    out = {}
    for key, days in PERIODS:
        row = {"fon": period_return(dates, prices, anchor, days)}
        if bench_df is not None:
            b = bench_df[bench_df["Tarih"] <= anchor]
            for label, col in BENCHMARK_COLS.items():
                if col in b.columns:
                    row[label] = period_return(b["Tarih"], b[col], anchor, days)
        out[key] = row
    return out


def build_price_history(fund_prices, max_points=1500):
    """Lightweight Charts formatı: [{time, value}, ...]. Çok uzun serileri seyreltir."""
    df = fund_prices[["Tarih", "Fiyat"]].dropna().sort_values("Tarih")
    if len(df) > max_points:
        step = max(1, len(df) // max_points)
        df = df.iloc[::step]
    return [
        {"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
        for d, v in zip(df["Tarih"], df["Fiyat"])
    ]


def build_flows_history(fund_prices):
    """Aylık: yatırımcı sayısı, toplam değer, net nakit giriş/çıkış (TL)."""
    df = fund_prices.copy()
    df["AyBaşı"] = df["Tarih"].values.astype("datetime64[M]")
    monthly = df.groupby("AyBaşı").agg(
        Kisi=("Kişi Sayısı", "last"),
        ToplamDeger=("Fon Toplam Değer", "last"),
        Pay=("Tedavüldeki Pay Sayısı", "last"),
        Fiyat=("Fiyat", "last"),
    ).reset_index().sort_values("AyBaşı")

    net_akis = [None]
    for i in range(1, len(monthly)):
        pay_start = monthly["Pay"].iloc[i - 1]
        pay_end = monthly["Pay"].iloc[i]
        fiyat_end = monthly["Fiyat"].iloc[i]
        if pd.notna(pay_start) and pd.notna(pay_end) and pd.notna(fiyat_end):
            net_akis.append(round(float((pay_end - pay_start) * fiyat_end), 2))
        else:
            net_akis.append(None)
    monthly["NetAkis"] = net_akis

    return {
        "aylar": [d.strftime("%Y-%m") for d in monthly["AyBaşı"]],
        "yatirimci_sayisi": [None if pd.isna(v) else int(v) for v in monthly["Kisi"]],
        "toplam_deger": [None if pd.isna(v) else round(float(v), 2) for v in monthly["ToplamDeger"]],
        "net_nakit_akisi": [None if pd.isna(v) else round(float(v), 2) for v in monthly["NetAkis"]],
    }


def build_allocation(alloc_df):
    """Son tarihli dağılım + zaman serisi (100'e normalize edilmiş yüzdeler)."""
    if alloc_df is None or alloc_df.empty:
        return None
    alloc_df = alloc_df.sort_values("Tarih")
    cat_cols = [c for c in alloc_df.columns if c not in ALLOC_EXCLUDE_COLS]

    # En son TARİH değil, en son DOLU satır — güncel gün henüz yayınlanmamışsa
    # (tüm kategoriler boş/null) bir önceki güne geri düşer.
    filled = alloc_df[alloc_df[cat_cols].notna().any(axis=1)]
    if filled.empty:
        latest = {}
    else:
        latest_row = filled.iloc[-1]
        latest = {
            c: round(float(latest_row[c]), 2)
            for c in cat_cols
            if pd.notna(latest_row[c]) and latest_row[c] > 0
        }
        latest = dict(sorted(latest.items(), key=lambda kv: -kv[1]))

    history = {
        "tarihler": [d.strftime("%Y-%m-%d") for d in alloc_df["Tarih"]],
        "seriler": {
            c: [None if pd.isna(v) else round(float(v), 2) for v in alloc_df[c]]
            for c in cat_cols
        },
    }
    return {"son_tarihli": latest, "gecmis": history}


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main():
    price_df = pd.read_parquet(PRICE_PATH)
    price_df["Tarih"] = pd.to_datetime(price_df["Tarih"]).dt.normalize()
    price_df = price_df[price_df["Fiyat"] > 0].sort_values(["Fon Kodu", "Tarih"])

    mapping = pd.read_excel(MAPPING_PATH)

    fon_bilgi = pd.read_parquet(FON_BILGI_PATH) if os.path.exists(FON_BILGI_PATH) else pd.DataFrame()

    alloc_all = None
    if os.path.exists(ALLOC_PATH):
        alloc_all = pd.read_parquet(ALLOC_PATH)
        alloc_all["Tarih"] = pd.to_datetime(alloc_all["Tarih"]).dt.normalize()

    bench_df = None
    if os.path.exists(BENCHMARK_PATH):
        bench_df = pd.read_parquet(BENCHMARK_PATH)
        bench_df["Tarih"] = pd.to_datetime(bench_df["Tarih"]).dt.normalize()
        bench_df = bench_df.sort_values("Tarih").reset_index(drop=True)

    # Fonlarca Skoru + alt skorlar (score_funds.py'deki aynı hesap)
    res, anchor = build_fund_metrics(price_df)
    res = res.merge(mapping, on=MAPPING_COLS["kod"], how="left")
    res = res[res[MAPPING_COLS["kategori"]].notna()]
    res = compute_scores(res)
    res_by_kod = res.set_index("Fon Kodu")

    os.makedirs(OUT_DIR, exist_ok=True)
    index_list = []

    for kod, fund_prices in price_df.groupby("Fon Kodu"):
        map_row = mapping[mapping[MAPPING_COLS["kod"]] == kod]
        if map_row.empty:
            continue
        map_row = map_row.iloc[0]

        bilgi_row = None
        if not fon_bilgi.empty:
            match = fon_bilgi[fon_bilgi["Fon Kodu"] == kod]
            if not match.empty:
                bilgi_row = match.iloc[0]

        skor_row = res_by_kod.loc[kod] if kod in res_by_kod.index else None

        fund_alloc = None
        if alloc_all is not None:
            fund_alloc = alloc_all[alloc_all["Fon Kodu"] == kod]

        card = {
            "fon_kodu": kod,
            "fon_adi": map_row.get(MAPPING_COLS["ad"]),
            "semsiye": map_row.get(MAPPING_COLS["semsiye"]),
            "kategori": map_row.get(MAPPING_COLS["kategori"]),
            "veri_tarihi": fund_prices["Tarih"].max().strftime("%Y-%m-%d"),

            "toplam_fon_degeri": float(fund_prices["Fon Toplam Değer"].iloc[-1])
                if pd.notna(fund_prices["Fon Toplam Değer"].iloc[-1]) else None,
            "yatirimci_sayisi": int(fund_prices["Kişi Sayısı"].iloc[-1])
                if pd.notna(fund_prices["Kişi Sayısı"].iloc[-1]) else None,

            "risk_degeri": (None if bilgi_row is None or pd.isna(bilgi_row.get("Risk_Degeri"))
                             else float(bilgi_row.get("Risk_Degeri"))),
            "stopaj_orani": (None if bilgi_row is None or pd.isna(bilgi_row.get("Stopaj_Orani"))
                              else float(bilgi_row.get("Stopaj_Orani"))),
            "yonetim_ucreti": (None if bilgi_row is None or pd.isna(bilgi_row.get("Uygulanan_Yonetim_Ucreti_%"))
                                 else float(bilgi_row.get("Uygulanan_Yonetim_Ucreti_%"))),

            "getiriler": build_returns_table(fund_prices),
            "fiyat_grafigi": build_price_history(fund_prices),
            "karsilastirma": build_compare_table(fund_prices, bench_df),
            "akislar": build_flows_history(fund_prices),
            "varlik_dagilimi": build_allocation(fund_alloc),

            "fonlarca_skoru": None if skor_row is None else {
                "kategori_skoru": None if pd.isna(skor_row.get("TEFAS_Skoru")) else round(float(skor_row["TEFAS_Skoru"]), 1),
                "kategori_sirasi": None if pd.isna(skor_row.get("Kategori_Sırası")) else int(skor_row["Kategori_Sırası"]),
                "alt_skorlar": {
                    "Momentum": _rnd(skor_row.get("Skor_Momentum")),
                    "Getiri": _rnd(skor_row.get("Skor_Getiri")),
                    "ParaAkışı": _rnd(skor_row.get("Skor_ParaAkışı")),
                    "Sharpe": _rnd(skor_row.get("Skor_Sharpe")),
                    "StdDev": _rnd(skor_row.get("Skor_StdDev")),
                },
            },
        }

        with open(os.path.join(OUT_DIR, f"{kod}.json"), "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=None, default=str, allow_nan=False)

        index_list.append({"kod": kod, "ad": card["fon_adi"], "kategori": card["kategori"]})

    with open(os.path.join(OUT_DIR, "_index.json"), "w", encoding="utf-8") as f:
        json.dump(index_list, f, ensure_ascii=False)

    print(f"{len(index_list)} fon için kart JSON'u üretildi -> {OUT_DIR}/")


def _rnd(v):
    return None if v is None or pd.isna(v) else round(float(v), 1)


if __name__ == "__main__":
    main()
