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

# Dönem sekmeleri: (anahtar, pandas DateOffset ya da None=yılbaşı)
# ÖNEMLİ: TEFAS "1 ay önce" derken TAKVİM AYINI kullanıyor (7 Ağustos -> 7 Temmuz),
# sabit 30 gün değil. Ay/yıl bazlı tüm dönemler bu yüzden DateOffset(months=/years=)
# ile hesaplanıyor — sadece Haftalık gün bazlı (7 gün) kalıyor, orada belirsizlik yok.
PERIODS = [
    ("1H", pd.DateOffset(days=7)), ("1A", pd.DateOffset(months=1)),
    ("3A", pd.DateOffset(months=3)), ("6A", pd.DateOffset(months=6)),
    ("YB", None), ("1Y", pd.DateOffset(years=1)),
    ("3Y", pd.DateOffset(years=3)), ("5Y", pd.DateOffset(years=5)),
]

BENCHMARK_COLS = {
    "USD": "USD_Alis", "EUR": "EUR_Alis", "BIST100": "BIST100",
    "TLREF": "TLREF_Endeks", "Altin": "Altin_Gram",
}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def period_return(series_dates, series_values, anchor_date, offset=None):
    """anchor_date'ten `offset` kadar öncesine (ya da yılbaşına) göre % getiri hesaplar.
    `offset` bir pd.DateOffset olmalı (örn. pd.DateOffset(months=1)) — TEFAS'ın
    kullandığı takvim ayı/yılı mantığıyla birebir uyumlu olsun diye.
    Serinin kendi son DOLU değerini kullanır — örn. TLREF birkaç gün gecikmeli
    yayınlanıyorsa, sadece o serinin kendi son dolu tarihine göre hesaplanır;
    diğer serileri veya dönemleri etkilemez."""
    valid = series_values.notna()
    dates_valid = series_dates[valid]
    values_valid = series_values[valid]
    if values_valid.empty:
        return None
    latest_val = values_valid.iloc[-1]

    if offset is None:
        # Yılbaşı (YTD): o yılın İLK işlem günü fiyatından bugüne.
        # TEFAS 31 Aralık fiyatını 2 Ocak'ta yayınladığı için, yıl bu yılın ilk
        # kaydından (>= 1 Ocak) başlar — 1 Ocak'a eşit/önceki (yani geçen yılın
        # 31 Aralık) değeri DEĞİL. Fon kartındaki aylık tablo "Toplam" ile uyumlu.
        yil_basi = pd.Timestamp(year=anchor_date.year, month=1, day=1)
        # Fon/seri o yılın başında zaten var mıydı? Yoksa (yıl içinde kurulmuş
        # bir fon gibi) "yılbaşından beri getiri" kavramı anlamsız — "-" dönmeli,
        # kuruluş tarihini yanlışlıkla "yılbaşı fiyatı" sayıp göstermemeli.
        ilk_veri = dates_valid.min()
        if ilk_veri > yil_basi + pd.Timedelta(days=10):
            return None
        gelecek = values_valid[dates_valid >= yil_basi]
        if gelecek.empty:
            return None
        past_val = gelecek.iloc[0]
        if past_val == 0:
            return None
        return round(float((latest_val / past_val - 1) * 100), 2)
    else:
        cutoff = anchor_date - offset
    past = values_valid[dates_valid <= cutoff]
    if past.empty:
        return None
    past_val = past.iloc[-1]
    if past_val == 0:
        return None
    return round(float((latest_val / past_val - 1) * 100), 2)


def build_returns_table(fund_prices):
    """Günlük/Haftalık/Aylık/3A/6A/Yılbaşı/1Y/3Y getiri tablosu.
    TEFAS'ın takvim ayı/yılı mantığına uyumlu (bkz. PERIODS notu)."""
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
        "Haftalık": period_return(dates, prices, anchor, pd.DateOffset(days=7)),
        "Aylık": period_return(dates, prices, anchor, pd.DateOffset(months=1)),
        "3 Ay": period_return(dates, prices, anchor, pd.DateOffset(months=3)),
        "6 Ay": period_return(dates, prices, anchor, pd.DateOffset(months=6)),
        "Yılbaşı": period_return(dates, prices, anchor, None),
        "1 Yıl": period_return(dates, prices, anchor, pd.DateOffset(years=1)),
        "3 Yıl": period_return(dates, prices, anchor, pd.DateOffset(years=3)),
    }


def build_compare_table(fund_prices, bench_df):
    """Her dönem sekmesi için PBR + her benchmark'ın % getirisi."""
    dates = fund_prices["Tarih"]
    prices = fund_prices["Fiyat"]
    anchor = dates.max()

    out = {}
    for key, offset in PERIODS:
        row = {"fon": period_return(dates, prices, anchor, offset)}
        if bench_df is not None:
            b = bench_df[bench_df["Tarih"] <= anchor]
            for label, col in BENCHMARK_COLS.items():
                if col in b.columns:
                    row[label] = period_return(b["Tarih"], b[col], anchor, offset)
        out[key] = row
    return out


def kisalt_unvan(ad):
    """Fon unvanındaki uzun parantez içi ifadeyi kısaltır (sadece görüntüleme
    amaçlı — kaynak veriyi değiştirmez). Örn: '... (HİSSE SENEDİ YOĞUN FON)'
    -> '... (HSYF)'."""
    if not ad:
        return ad
    return ad.replace("(HİSSE SENEDİ YOĞUN FON)", "(HSYF)")


def kisalt_semsiye(s):
    """'Şemsiye' alanındaki tekrarlayan 'Şemsiye Fonu' ibaresini kaldırır.
    Örn: 'Hisse Senedi Şemsiye Fonu' -> 'Hisse Senedi'."""
    if not s:
        return s
    return s.replace(" Şemsiye Fonu", "").replace("Şemsiye Fonu", "").strip()


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


def build_benchmark_series(bench_df, max_points=1500):
    """Tüm fonlar için PAYLAŞILAN tek bir benchmark zaman serisi dosyası üretir
    (her fon JSON'unda tekrarlanmasın diye ayrı dosya). Her seri kendi boş
    olmayan (dropna) noktalarını içerir — tarihler seriler arasında birebir
    aynı olmak zorunda değil, frontend en yakın tarihi kendi eşleştirir."""
    if bench_df is None or bench_df.empty:
        return {}
    out = {}
    for label, col in BENCHMARK_COLS.items():
        if col not in bench_df.columns:
            continue
        s = bench_df[["Tarih", col]].dropna().sort_values("Tarih")
        if len(s) > max_points:
            step = max(1, len(s) // max_points)
            s = s.iloc[::step]
        out[label] = [
            {"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
            for d, v in zip(s["Tarih"], s[col])
        ]
    return out


def build_flows_history(fund_prices, gunluk_gun=35):
    """Aylık seri (uzun geçmiş için) + günlük seri (son `gunluk_gun` gün, haftalık/
    aylık gün-gün görünüm için). Her ikisinde: yatırımcı sayısı, toplam değer,
    net nakit giriş/çıkış (TL)."""
    df = fund_prices.copy().sort_values("Tarih")

    # --- Aylık seri (mevcut davranış) ---
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

    # --- Günlük seri (son gunluk_gun gün) ---
    d = df.dropna(subset=["Fiyat"]).copy()
    # Net günlük akış: (bugünkü pay - dünkü pay) * bugünkü fiyat
    d["PayOnceki"] = d["Tedavüldeki Pay Sayısı"].shift(1)
    d["NetAkisGun"] = (d["Tedavüldeki Pay Sayısı"] - d["PayOnceki"]) * d["Fiyat"]
    d_tail = d.tail(gunluk_gun)

    return {
        "aylar": [dt.strftime("%Y-%m") for dt in monthly["AyBaşı"]],
        "yatirimci_sayisi": [None if pd.isna(v) else int(v) for v in monthly["Kisi"]],
        "toplam_deger": [None if pd.isna(v) else round(float(v), 2) for v in monthly["ToplamDeger"]],
        "net_nakit_akisi": [None if pd.isna(v) else round(float(v), 2) for v in monthly["NetAkis"]],
        "gunluk": {
            "gunler": [dt.strftime("%Y-%m-%d") for dt in d_tail["Tarih"]],
            "yatirimci_sayisi": [None if pd.isna(v) else int(v) for v in d_tail["Kişi Sayısı"]],
            "toplam_deger": [None if pd.isna(v) else round(float(v), 2) for v in d_tail["Fon Toplam Değer"]],
            "net_nakit_akisi": [None if pd.isna(v) else round(float(v), 2) for v in d_tail["NetAkisGun"]],
        },
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
            if pd.notna(latest_row[c]) and latest_row[c] != 0
        }
        latest = dict(sorted(latest.items(), key=lambda kv: -abs(kv[1])))

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

    # TEFAS'a açık fon kodları — her fonun açık/kapalı durumunu işaretlemek için.
    # Dosya yoksa (veya boşsa) None kalır ve durum bilgisi "bilinmiyor" (None) olur.
    acik_fon_kodlari = None
    ACIK_PATH = "tefas_acik_fonlar.parquet"
    if os.path.exists(ACIK_PATH):
        try:
            acik_df = pd.read_parquet(ACIK_PATH)
            if not acik_df.empty and "Fon Kodu" in acik_df.columns:
                acik_fon_kodlari = set(acik_df["Fon Kodu"].dropna().astype(str))
                print(f"[export] {len(acik_fon_kodlari)} açık fon kodu yüklendi.")
        except Exception as e:
            print(f"[export] {ACIK_PATH} okunamadı ({e}), açık/kapalı durumu işaretlenmeyecek.")

    alloc_all = None
    fon_adlari = {}  # TEFAS'ın kendi 'Fon Unvanı' verisinden isim haritası —
                      # manuel eşleştirme dosyasına bağımlı kalmasın diye
    if os.path.exists(ALLOC_PATH):
        alloc_all = pd.read_parquet(ALLOC_PATH)
        alloc_all["Tarih"] = pd.to_datetime(alloc_all["Tarih"]).dt.normalize()
        if "Fon Unvanı" in alloc_all.columns:
            isim_df = alloc_all.dropna(subset=["Fon Unvanı"]).sort_values("Tarih")
            fon_adlari = isim_df.groupby("Fon Kodu")["Fon Unvanı"].last().to_dict()

    bench_df = None
    if os.path.exists(BENCHMARK_PATH):
        bench_df = pd.read_parquet(BENCHMARK_PATH)
        bench_df["Tarih"] = pd.to_datetime(bench_df["Tarih"]).dt.normalize()
        bench_df = bench_df.sort_values("Tarih").reset_index(drop=True)

    os.makedirs(OUT_DIR, exist_ok=True)

    # Tüm fonlar için PAYLAŞILAN tek benchmark dosyası (her fon JSON'unda tekrar etmesin)
    with open(os.path.join(OUT_DIR, "_benchmarks.json"), "w", encoding="utf-8") as f:
        json.dump(build_benchmark_series(bench_df), f, ensure_ascii=False, allow_nan=False)

    # Fonlarca Skoru + alt skorlar (score_funds.py'deki aynı hesap)
    res, anchor = build_fund_metrics(price_df, bench_df)
    res = res.merge(mapping, on=MAPPING_COLS["kod"], how="left")
    res = res[res[MAPPING_COLS["kategori"]].notna()]
    # Kapalı fonlar puanlamaya girmez — score_funds.py ile birebir tutarlı olsun diye
    # skor hesabından önce çıkarılır; kartlarında skor "None" olur (aşağıda skor_row
    # bulunamayınca zaten fonlarca_skoru=None yazılıyor).
    if acik_fon_kodlari is not None:
        res = res[res[MAPPING_COLS["kod"]].isin(acik_fon_kodlari)]
    res = compute_scores(res)
    res_by_kod = res.set_index("Fon Kodu")

    index_list = []

    for kod, fund_prices in price_df.groupby("Fon Kodu"):
        map_row = mapping[mapping[MAPPING_COLS["kod"]] == kod]
        map_row = map_row.iloc[0] if not map_row.empty else None

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
            "fon_adi": kisalt_unvan(
                fon_adlari.get(kod) or (map_row.get(MAPPING_COLS["ad"]) if map_row is not None else None)
            ),
            "semsiye": kisalt_semsiye(map_row.get(MAPPING_COLS["semsiye"])) if map_row is not None else None,
            "kategori": map_row.get(MAPPING_COLS["kategori"]) if map_row is not None else None,
            "veri_tarihi": fund_prices["Tarih"].max().strftime("%Y-%m-%d"),

            "tefas_acik": (None if acik_fon_kodlari is None else (kod in acik_fon_kodlari)),

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

        index_list.append({"kod": kod, "ad": card["fon_adi"], "kategori": card["kategori"],
                            "acik": card["tefas_acik"]})

    with open(os.path.join(OUT_DIR, "_index.json"), "w", encoding="utf-8") as f:
        json.dump(index_list, f, ensure_ascii=False)

    print(f"{len(index_list)} fon için kart JSON'u üretildi -> {OUT_DIR}/")


def _rnd(v):
    return None if v is None or pd.isna(v) else round(float(v), 1)


if __name__ == "__main__":
    main()
