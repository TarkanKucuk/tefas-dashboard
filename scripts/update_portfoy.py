import pandas as pd
from tefasfon import get_portfolio
from datetime import datetime, timedelta
import os
DATA_PATH = "tefas_portfoy_dagilim.parquet"
# Her çalıştırmada son kaç günü yeniden kontrol edelim (TEFAS'ın bazı günleri
# geç yayınlaması ya da tek seferlik API hatası durumunda kendiliğinden düzelsin diye)
GERI_GUN = 20
# Kısaltmalardan Orijinal Türkçe Başlıklara Çeviri
KOLON_MAP = {
"fonKodu": "Fon Kodu",
"fonUnvan": "Fon Unvanı",
"tarih": "Tarih",
"hs": "His.Sen.",
"dt": "Dev.Tah.",
"hb": "Haz.Bon.",
"vdm": "VDMK",
"vmtl": "Mevd.(TL)",
"tr": "Ters Repo",
"byf": "BYF",
"km": "Kıy.Maden",
"kkstl": "Kam.Kira Sert. (TL)",
"osks": "Ö.S.Kira Sert.",
"d": "Diğer",
"bpp": "BPP",
"btaa": "BİST Tah.İşl.Paz.Alım",
"btas": "BİST Tah.İşl.Paz.Satım",
"fb": "Fin.Bon.",
"gas": "G.Menk.Sert.",
"gsykb": "GSYF",
"gsyy": "Gir.Ser.Yatırımları",
"gykb": "GYF",
"kba": "Kam.Dış Borç.",
"khau": "Kat.Hes.(Altın)",
"khd": "Kat.Hes.(Döviz)",
"khtl": "Kat.Hes.(TL)",
"kksd": "Kam.Kira Sert. (Döviz)",
"kksyd": "Kam.Y.Dışı Kira Sert.",
"kmbyf": "Kıy.Mad.Cins.BYF",
"kmkba": "Kıy.Mad.Cins.Kam.Borç.",
"kmkks": "Kıy.Mad.Cins.Kam.Kira Sert.",
"kibd": "Döv.Cins.Kam.İç Borç.",
"ost": "ÖS Tahvil",
"r": "Repo",
"tpp": "TPP",
"vmau": "Mevd.(Altın)",
"vmd": "Mevd.(Döviz)",
"vint": "Vad.İşl.Nak.Tem.",
"ybkb": "Yab.Kamu Borç.",
"ybosb": "Yab.ÖS Bor.",
"ybyf": "Yab.BYF",
"yhs": "Yab.His.Sen.",
"yyf": "YF Kat.Pay.",
"oksyd": "ÖS Y.Dışı Kira Sert.",
"osdb": "ÖS Dış Borç.",
"eut": "Euro Tahvil",
"gyy": "G.Menk.Yat.Ort.",
}
def gun_verisi_cek(tarih_str):
    """Tek bir gün için portföy verisini çeker. Geniş aralıklı istekler bazı
    günleri sessizce boş döndürebiliyor (teşhis edildi) — bu yüzden her günü
    ayrı ayrı, tek başına istiyoruz; bu şekilde güvenilir çalıştığı doğrulandı."""
    try:
        df = get_portfolio(fund_type="SEC", start_date=tarih_str, end_date=tarih_str)
    except Exception as e:
        print(f"  {tarih_str}: HATA ({e})")
        return None
    if df is None or df.empty:
        print(f"  {tarih_str}: veri yok (tatil/hafta sonu olabilir)")
        return None
    return df


def main():
    bugun_dt = datetime.today()
    tarihler = [(bugun_dt - timedelta(days=i)) for i in range(GERI_GUN, -1, -1)]

    # Eski veri varsa oku
    if os.path.exists(DATA_PATH):
        hist = pd.read_parquet(DATA_PATH)
        print(f"Eski veri yüklendi: {len(hist)} satır")
    else:
        hist = pd.DataFrame()
        print("Yeni veri dosyası oluşturulacak.")

    print(f"Kontrol edilen {len(tarihler)} gün: {tarihler[0].strftime('%d.%m.%Y')} -> {tarihler[-1].strftime('%d.%m.%Y')}")
    print("TEFAS'tan portföy dağılımı GÜNLÜK olarak çekiliyor...")
    gunluk_df_listesi = []
    for t in tarihler:
        df_gun = gun_verisi_cek(t.strftime("%d.%m.%Y"))
        if df_gun is not None:
            gunluk_df_listesi.append(df_gun)

    if not gunluk_df_listesi:
        print("Hiçbir gün için veri alınamadı.")
        return
    df = pd.concat(gunluk_df_listesi, ignore_index=True)

    ozel_kolonlar = {"fonKodu", "fonUnvan", "tarih", "bilFiyat"}
    bilinen_kodlar = set(KOLON_MAP.keys())
    # --- YENİ: KOLON_MAP'te olmayan (TEFAS'ın sonradan eklediği) sayısal
    # kategori kolonlarını kaybetmeyelim — hepsini "Diğer"e topluyoruz.
    bilinmeyen_kolonlar = [c for c in df.columns if c not in bilinen_kodlar and c not in ozel_kolonlar]
    if bilinmeyen_kolonlar:
        print(f"Not: KOLON_MAP'te olmayan yeni kolonlar bulundu, 'Diğer'e toplanıyor: {bilinmeyen_kolonlar}")
        for kol in bilinmeyen_kolonlar:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")
        # min_count=1: bir satırda TÜMÜ boşsa sonuç 0 değil NaN olsun — yoksa
        # "veri yok" durumu yanlışlıkla "Diğer=0, yani dolu" gibi görünür ve
        # aşağıdaki boş-gün tespiti bunu kaçırır.
        df["_bilinmeyen_toplam"] = df[bilinmeyen_kolonlar].sum(axis=1, skipna=True, min_count=1)
    else:
        df["_bilinmeyen_toplam"] = float("nan")

    # Sadece sayısal kolonları yüzde formatına çevir
    sayisal_kolonlar = [k for k in KOLON_MAP.keys() if k not in ["fonKodu", "fonUnvan", "tarih"]]
    for kol in sayisal_kolonlar:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")
    # Türkçe başlıklara çevir
    df = df.rename(columns=KOLON_MAP)
    df["Tarih"] = pd.to_datetime(df["Tarih"])
    # İstemediğimiz kolonları at: fiyat bilgisi (bilFiyat) ve zaten "Diğer"e
    # topladığımız bilinmeyen ham kolonlar. Geri kalan HER ŞEYİ (Türkçeye
    # çevrilmiş tüm kategori kolonları dahil) olduğu gibi koruyoruz.
    df = df.drop(columns=[c for c in bilinmeyen_kolonlar if c in df.columns], errors="ignore")
    df = df.drop(columns=["bilFiyat"], errors="ignore")

    if "Diğer" not in df.columns:
        df["Diğer"] = float("nan")
    # Aynı min_count=1 mantığı: ikisi de boşsa sonuç NaN kalsın (0 değil).
    df["Diğer"] = df[["Diğer", "_bilinmeyen_toplam"]].sum(axis=1, skipna=True, min_count=1)
    df = df.drop(columns=["_bilinmeyen_toplam"])

    # Bir gün için tüm fonlarda tüm kategori kolonları boşsa (ör. bugünün henüz
    # kapanmamış/kesinleşmemiş verisi), o günü bu partiden çıkar — eski veriyi bozmasın.
    sayisal_kolonlar_tr = [KOLON_MAP[k] for k in sayisal_kolonlar if KOLON_MAP[k] in df.columns] + ["Diğer"]
    if sayisal_kolonlar_tr and "Tarih" in df.columns:
        gun_bazinda_dolu = df.groupby("Tarih")[sayisal_kolonlar_tr].apply(lambda g: g.notna().any().any())
        bos_gunler = gun_bazinda_dolu[~gun_bazinda_dolu].index
        if len(bos_gunler):
            print(f"⚠️ Şu tarihler için TEFAS verisi henüz yayınlanmamış/boş görünüyor, atlanıyor: "
                  f"{[d.strftime('%d.%m.%Y') for d in bos_gunler]}")
            df = df[~df["Tarih"].isin(bos_gunler)]
    if df.empty:
        print("Bu aralıkta kaydedilecek dolu veri yok — hiçbir şey yazılmadı.")
        return

    # Yeni veriyi eski veriye ekle
    hist = hist.copy()
    hist["_kaynak"] = 0   # eski veri
    df["_kaynak"] = 1     # yeni çekilen veri
    combined = pd.concat([hist, df], ignore_index=True)

    # ÖNEMLİ: Aynı Fon Kodu+Tarih için iki satır varsa (biri eski, biri yeni),
    # DOLU olanı her zaman tercih et — hangisi eski hangisi yeni olduğuna bakmadan.
    # Böylece geniş aralıklı yeniden-çekimler sırasında bazı fon/gün kombinasyonları
    # boş dönerse bile, elimizdeki iyi (dolu) veri yanlışlıkla silinmez.
    # İkisi de doluysa ya da ikisi de boşsa, en yeni çekimi (_kaynak=1) tercih et.
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
    yeni_satir = len(df)
    toplam_satir = len(combined)
    print(f"✅ {yeni_satir} satır işlendi/güncellendi. Toplam: {toplam_satir} satır.")
if __name__ == "__main__":
    main()
