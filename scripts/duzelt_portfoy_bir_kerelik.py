"""
BİR KERELİK DÜZELTME — tefas_portfoy_dagilim.parquet.

Sorun: bazı fonların varlık dağılımı verisi geride kalmış (çoğu fon 24 Ağustos,
bazıları örn. HVZ 25 Ağustos'ta takılı). Bu script, 25 Ağustos 2026'dan BUGÜNE
kadar her günü — "zaten dolu mu" kontrolü yapmadan — TEK TEK ZORLA yeniden çeker
ve mevcut parquet'e işler.

Çalışan günlük script'e (update_portfoy.py) hiç dokunmaz; oradan sadece aynı
çekme fonksiyonunu, kolon haritasını ve dosya yolunu ödünç alır — böylece üretilen
veri günlük pipeline'la BİREBİR aynı biçimde işlenir.

Birleştirme mantığı update_portfoy.py ile aynıdır: aynı Fon Kodu + Tarih için
DOLU satır her zaman tercih edilir; yani bu yeniden-çekim, elde zaten dolu olan
hiçbir veriyi boşla ezmez, sadece eksik/boş günleri doldurur.

KULLANIM: GitHub Actions'ta bir kez çalıştır (TEFAS erişimi orada var), sonra
işini bitirince bu dosyayı repodan silebilirsin.
"""
import pandas as pd
from datetime import datetime, timedelta

# Çalışan günlük script'ten ödünç al (kod tekrarını ve tutarsızlığı önlemek için)
from update_portfoy import KOLON_MAP, gun_verisi_cek, DATA_PATH

# 25 Ağustos 2026'dan itibaren (dahil) bugüne kadar zorla çekilecek
BASLANGIC = datetime(2026, 8, 25)


def main():
    bugun = datetime.today()
    if not __import__("os").path.exists(DATA_PATH):
        print(f"{DATA_PATH} bulunamadı — düzeltilecek dosya yok.")
        return
    hist = pd.read_parquet(DATA_PATH)
    print(f"Mevcut veri: {len(hist)} satır, en son tarih: {pd.to_datetime(hist['Tarih']).max().date()}")

    # BASLANGIC -> bugün arasındaki HER günü zorla dene (hafta sonu/tatil boş döner, atlanır)
    tarihler = []
    t = BASLANGIC
    while t <= bugun:
        tarihler.append(t)
        t += timedelta(days=1)

    print(f"{BASLANGIC.date()} - {bugun.date()} arası {len(tarihler)} gün ZORLA yeniden çekilecek...")
    gunluk_df_listesi = []
    for t in tarihler:
        df_gun = gun_verisi_cek(t.strftime("%d.%m.%Y"))
        if df_gun is not None:
            gunluk_df_listesi.append(df_gun)
            print(f"  {t.strftime('%d.%m.%Y')}: {len(df_gun)} satır çekildi.")

    if not gunluk_df_listesi:
        print("Hiçbir gün için veri alınamadı — dosya değiştirilmedi.")
        return

    df = pd.concat(gunluk_df_listesi, ignore_index=True)

    # --- Kolon işleme: update_portfoy.py ile BİREBİR AYNI ---
    ozel_kolonlar = {"fonKodu", "fonUnvan", "tarih", "bilFiyat"}
    bilinen_kodlar = set(KOLON_MAP.keys())

    bilinmeyen_kolonlar = [c for c in df.columns if c not in bilinen_kodlar and c not in ozel_kolonlar]
    if bilinmeyen_kolonlar:
        print(f"Not: KOLON_MAP'te olmayan yeni kolonlar 'Diğer'e toplanıyor: {bilinmeyen_kolonlar}")
        for kol in bilinmeyen_kolonlar:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")
        df["_bilinmeyen_toplam"] = df[bilinmeyen_kolonlar].sum(axis=1, skipna=True, min_count=1)
    else:
        df["_bilinmeyen_toplam"] = float("nan")

    sayisal_kolonlar = [k for k in KOLON_MAP.keys() if k not in ["fonKodu", "fonUnvan", "tarih"]]
    for kol in sayisal_kolonlar:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")

    df = df.rename(columns=KOLON_MAP)
    df["Tarih"] = pd.to_datetime(df["Tarih"])

    df = df.drop(columns=[c for c in bilinmeyen_kolonlar if c in df.columns], errors="ignore")
    df = df.drop(columns=["bilFiyat"], errors="ignore")

    if "Diğer" not in df.columns:
        df["Diğer"] = float("nan")
    df["Diğer"] = df[["Diğer", "_bilinmeyen_toplam"]].sum(axis=1, skipna=True, min_count=1)
    df = df.drop(columns=["_bilinmeyen_toplam"])

    sayisal_kolonlar_tr = [KOLON_MAP[k] for k in sayisal_kolonlar if KOLON_MAP[k] in df.columns] + ["Diğer"]
    if sayisal_kolonlar_tr and "Tarih" in df.columns:
        gun_bazinda_dolu = df.groupby("Tarih")[sayisal_kolonlar_tr].apply(lambda g: g.notna().any().any())
        bos_gunler = gun_bazinda_dolu[~gun_bazinda_dolu].index
        if len(bos_gunler):
            print(f"⚠️ Şu tarihler boş görünüyor, atlanıyor: {[d.strftime('%d.%m.%Y') for d in bos_gunler]}")
            df = df[~df["Tarih"].isin(bos_gunler)]

    if df.empty:
        print("Çekilen veride dolu gün yok — dosya değiştirilmedi.")
        return

    # --- Birleştirme: DOLU satırı tercih et (update_portfoy.py ile aynı) ---
    hist = hist.copy()
    hist["Tarih"] = pd.to_datetime(hist["Tarih"])
    hist["_kaynak"] = 0
    df["_kaynak"] = 1
    combined = pd.concat([hist, df], ignore_index=True)

    dolu_kontrol_kolonlari = [c for c in sayisal_kolonlar_tr if c in combined.columns]
    if dolu_kontrol_kolonlari:
        combined["_dolu"] = combined[dolu_kontrol_kolonlari].notna().any(axis=1)
    else:
        combined["_dolu"] = False
    combined = combined.sort_values(["Fon Kodu", "Tarih", "_dolu", "_kaynak"])
    combined = combined.drop_duplicates(subset=["Fon Kodu", "Tarih"], keep="last")
    combined = combined.drop(columns=["_dolu", "_kaynak"])
    combined = combined.sort_values(["Fon Kodu", "Tarih"])
    combined.to_parquet(DATA_PATH, index=False)

    print(f"✅ Düzeltme tamam. {len(df)} satır işlendi. Toplam: {len(combined)} satır. "
          f"Yeni en son tarih: {combined['Tarih'].max().date()}")


if __name__ == "__main__":
    main()
