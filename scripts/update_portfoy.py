import pandas as pd
from tefasfon import get_portfolio
from datetime import datetime, timedelta
import os
import time

DATA_PATH = "tefas_portfoy_dagilim.parquet"

# Her çalıştırmada son kaç günü yeniden kontrol edelim (TEFAS'ın bazı günleri
# geç yayınlaması ya da tek seferlik API hatası durumunda kendiliğinden düzelsin diye)
GERI_GUN = 20

# "Bu gün için normalde kaç fon veri vermeliydi" tahmininde kullanılan pencere
# ve eşik — hem eksik gün tespitinde hem de aynı çalıştırma içindeki tekrar
# deneme mantığında (aşağıda) kullanılır.
BEKLENEN_PENCERE = 15
FON_ESIK_ORANI = 0.95

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

# Tüm sayısal kategori kolonlarının Türkçe adları (Fon Kodu/Unvanı/Tarih hariç) —
# hem yeni çekilen veriyi işlerken hem de "hangi günler zaten tam dolu" kontrolünde kullanılır.
TUM_KATEGORI_KOLONLARI = [v for k, v in KOLON_MAP.items() if k not in ("fonKodu", "fonUnvan", "tarih")]


def beklenen_fon_sayisi_hesapla(hist, pencere_gun=15):
    """Son `pencere_gun` gün içinde en az bir kez veri vermiş benzersiz fon
    sayısını döndürür — "bu gün için normalde kaç fon veri vermeliydi"
    tahminimiz budur."""
    if hist.empty or "Tarih" not in hist.columns:
        return 0
    hist = hist.copy()
    hist["Tarih"] = pd.to_datetime(hist["Tarih"]).dt.normalize()
    son_tarih = hist["Tarih"].max()
    pencere_baslangic = son_tarih - pd.Timedelta(days=pencere_gun)
    return hist[hist["Tarih"] >= pencere_baslangic]["Fon Kodu"].nunique()


def eksik_tarihleri_bul(hist, tarihler):
    """`tarihler` listesindeki hangi günlerin hâlâ tekrar çekilmesi gerektiğini
    bulur: hist'te o tarih için hiç satır yoksa, satırlar VAR ama en az biri
    boşsa (tüm kategorileri NaN), YA DA o tarihte satırı olan fon sayısı
    "beklenen" fon sayısından belirgin şekilde azsa (bazı fonlar o gün için
    HİÇ satır bile almamış demektir), o tarih 'eksik/tamamlanmamış' sayılır.

    ÖNEMLİ DÜZELTME: Önceki hâli sadece "o tarihte VAR OLAN satırlar dolu mu"
    diye bakıyordu — bir fon o gün için hiç satır almadıysa (TEFAS o fonu o
    gün hiç döndürmediyse), bu durum hiç yakalanmıyordu ve o gün "tamam"
    sayılıp bir daha asla tekrar denenmiyordu. Bu yüzden bazı fonlar sürekli
    belirli günleri kaçırıp asla telafi edemiyordu. Artık "fon sayısı" kontrolü
    de ekleniyor: son BEKLENEN_PENCERE gün içinde en az bir kez veri vermiş
    TÜM fonların kümesi "beklenen" kabul edilir; bir tarihte bu kümenin
    FON_ESIK_ORANI'ndan azı için satır varsa, o tarih eksik sayılır."""
    if hist.empty or "Tarih" not in hist.columns:
        return tarihler

    mevcut_kolonlar = [c for c in TUM_KATEGORI_KOLONLARI if c in hist.columns]
    if not mevcut_kolonlar:
        return tarihler

    hist_check = hist.copy()
    hist_check["Tarih"] = pd.to_datetime(hist_check["Tarih"]).dt.normalize()
    hist_check["_dolu"] = hist_check[mevcut_kolonlar].notna().any(axis=1)
    gun_tam_dolu = hist_check.groupby("Tarih")["_dolu"].all()

    # "Beklenen" fon kümesi: son BEKLENEN_PENCERE gün içinde en az bir kez veri
    # vermiş tüm fonlar. Bir tarihte bu kümenin çoğu için satır yoksa, o tarih
    # "genel olarak dolu" görünse bile (var olan satırlar dolu diye) eksik sayılır.
    beklenen_sayi = beklenen_fon_sayisi_hesapla(hist_check, BEKLENEN_PENCERE)
    gun_fon_sayisi = hist_check.groupby("Tarih")["Fon Kodu"].nunique()

    eksikler = []
    for t in tarihler:
        t_norm = pd.Timestamp(t.date())
        if t_norm not in gun_tam_dolu.index or not gun_tam_dolu.loc[t_norm]:
            eksikler.append(t)
            continue
        if beklenen_sayi > 0:
            mevcut_sayi = gun_fon_sayisi.get(t_norm, 0)
            if mevcut_sayi < beklenen_sayi * FON_ESIK_ORANI:
                eksikler.append(t)
    return eksikler


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
    tarihler_hepsi = [(bugun_dt - timedelta(days=i)) for i in range(GERI_GUN, -1, -1)]

    # Eski veri varsa oku
    if os.path.exists(DATA_PATH):
        hist = pd.read_parquet(DATA_PATH)
        print(f"Eski veri yüklendi: {len(hist)} satır")
    else:
        hist = pd.DataFrame()
        print("Yeni veri dosyası oluşturulacak.")

    # Zaten TAM DOLU olan günleri tekrar sorgulamaya gerek yok — sadece
    # hiç çekilmemiş ya da hâlâ boşluk içeren günleri tekrar deniyoruz.
    tarihler = eksik_tarihleri_bul(hist, tarihler_hepsi)
    atlanan = len(tarihler_hepsi) - len(tarihler)
    if atlanan:
        print(f"{atlanan} gün zaten tam dolu olduğu için atlandı.")
    if not tarihler:
        print("Kontrol edilecek eksik/yeni gün yok — hiçbir istek atılmadı.")
        return

    print(f"Kontrol edilecek {len(tarihler)} gün: {tarihler[0].strftime('%d.%m.%Y')} -> {tarihler[-1].strftime('%d.%m.%Y')}")
    print("TEFAS'tan portföy dağılımı GÜNLÜK olarak çekiliyor...")
    beklenen_sayi = beklenen_fon_sayisi_hesapla(hist, BEKLENEN_PENCERE)
    gunluk_df_listesi = []
    for t in tarihler:
        tarih_str = t.strftime("%d.%m.%Y")
        en_iyi_df = None
        en_iyi_fon_sayisi = -1
        for deneme in range(3):  # ilk deneme + 2 ek tekrar
            df_gun = gun_verisi_cek(tarih_str)
            if df_gun is None:
                break  # kesin "veri yok" (tatil/hafta sonu) — tekrar denemeye değmez
            fon_sayisi = df_gun["fonKodu"].nunique()
            if fon_sayisi > en_iyi_fon_sayisi:
                en_iyi_df, en_iyi_fon_sayisi = df_gun, fon_sayisi
            # Yeterince dolu geldiyse (ya da beklenen sayı bilinmiyorsa) daha
            # fazla denemeye gerek yok.
            if beklenen_sayi == 0 or fon_sayisi >= beklenen_sayi * FON_ESIK_ORANI:
                break
            if deneme < 2:
                print(f"  {tarih_str}: sadece {fon_sayisi}/{beklenen_sayi} fon geldi, "
                      f"TEFAS'ın eksik yayınlamış olabileceğinden 15 sn sonra tekrar denenecek...")
                time.sleep(15)
        if en_iyi_df is not None and en_iyi_fon_sayisi < beklenen_sayi * FON_ESIK_ORANI and beklenen_sayi > 0:
            print(f"  {tarih_str}: 3 denemeden sonra hâlâ eksik ({en_iyi_fon_sayisi}/{beklenen_sayi} fon) — "
                  f"yine de gelen veri kaydedilecek, sonraki çalıştırmalarda tekrar denenecek.")
        if en_iyi_df is not None:
            gunluk_df_listesi.append(en_iyi_df)

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
