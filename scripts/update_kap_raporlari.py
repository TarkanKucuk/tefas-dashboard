"""
KAP'ın (Kamuyu Aydınlatma Platformu) kendi resmi ama dokümante edilmemiş
bildirim arama API'sini kullanarak, her TEFAS fonu için aylık "Portföy Dağılım
Raporu" bildirimlerinin KAP bildirim numarasını (disclosureIndex) toplar.

Neden böyle çalışır (önemli):
- Portföy yönetim şirketleri, bir önceki ayın dağılım raporunu HER AYIN
  1-10'u arasında KAP'a yüklüyor; 10'undan sonra yeni yükleme olmuyor.
- Bu yüzden: dosya hiç yoksa (ilk çalıştırma) geçmiş 6 ayı tek tek tarayıp
  doldurur. Dosya zaten varsa, sadece bugün ayın 1-10'u arasındaysa bu ayın
  (henüz gelmiş olabilecek) raporunu arar; 11'inden sonra hiç istek atmadan
  çıkar — gereksiz yük bindirmemek için.
- API'nin kendisi KAP'ın herkese açık, kimlik doğrulama gerektirmeyen
  (ama resmi olarak dokümante edilmemiş) bir uç noktası: KAP herhangi bir
  an bunu değiştirebilir/kısıtlayabilir; bu göz önünde bulundurulmalı.
"""
import requests
import pandas as pd
import time
from datetime import date, timedelta

OUT_PATH = "kap_raporlari.parquet"
BASE_URL = "https://www.kap.org.tr"
CRITERIA_URL = f"{BASE_URL}/tr/api/disclosure/members/byCriteria"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": f"{BASE_URL}/tr/bildirim-sorgu",
}
KEEP_MONTHS = 6  # her fon için en fazla saklanacak ay sayısı


def _warmup_session(session):
    """KAP'ın WAF'ı, önce sıradan bir GET ile oturum/çerez oluşturulmasını
    daha toleranslı karşılıyor (aksi halde bağlantı zaman aşımına uğrayabiliyor)."""
    try:
        session.get(f"{BASE_URL}/tr/bildirim-sorgu", headers=HEADERS, timeout=20)
    except Exception:
        pass


def fetch_window(session, from_date, to_date, deneme=3):
    """[from_date, to_date] aralığındaki YATIRIM FONU (YF) bildirimlerini döner.
    'fundTypeList': ['YF'] olmadan sorgu sadece BIST şirketi bildirimlerini
    döndürüyordu — bu, KAP'ın arama arayüzü tarayıcıdan izlenerek bulundu."""
    body = {
        "fromDate": from_date.isoformat(),
        "toDate": to_date.isoformat(),
        "discIndex": [],
        "disclosureClass": "",
        "fromSrc": False,
        "fundOidList": [],
        "fundTypeList": ["YF"],
        "isLate": "",
        "mkkMemberOidList": [],
        "passiveFundOidList": [],
        "srcCategory": "",
        "subjectList": [],
    }
    for i in range(1, deneme + 1):
        try:
            resp = session.post(CRITERIA_URL, headers=HEADERS, json=body, timeout=30)
            print(f"  [debug] HTTP durum kodu: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                fon_kodlu = [b for b in data if b.get("fundCode")]
                subjects = sorted(set(b.get("subject") for b in fon_kodlu if b.get("subject")))
                print(f"  [debug] Toplam bildirim: {len(data)}, fundCode dolu olan: {len(fon_kodlu)}")
                print(f"  [debug] fundCode dolu bildirimlerdeki benzersiz 'subject' değerleri: {subjects[:15]}")
                if fon_kodlu:
                    print(f"  [debug] Örnek kayıt: {fon_kodlu[0]}")
                else:
                    from collections import Counter
                    tur_dagilimi = Counter(b.get("disclosureType") for b in data)
                    print(f"  [debug] fundCode hiç yok — dönen 2000 kaydın disclosureType dağılımı: {tur_dagilimi.most_common(10)}")
                    if data:
                        print(f"  [debug] Örnek (fon olmayan) kayıt: {data[0]}")
                return data
            print(f"  [debug] Beklenmeyen yanıt tipi: {type(data)} -> {str(data)[:300]}")
            return []
        except Exception as e:
            print(f"  Deneme {i}/{deneme} başarısız ({from_date}–{to_date}): {e}")
            time.sleep(2)
    return []


def extract_portfoy_raporlari(bildirimler):
    """'Portföy Dağılım Raporu' bildirimlerini, fon kodu -> (yıl, ay, disclosureIndex,
    publishDate) şeklinde ayıklar."""
    sonuc = []
    for b in bildirimler:
        if b.get("subject") != "Portföy Dağılım Raporu":
            continue
        kod = b.get("fundCode")
        if not kod:
            continue
        yil, ay, idx = b.get("year"), b.get("period"), b.get("disclosureIndex")
        if yil is None or ay is None or idx is None:
            continue
        sonuc.append({
            "Fon Kodu": kod,
            "Yil": int(yil),
            "Ay": int(ay),
            "disclosureIndex": int(idx),
            "publishDate": b.get("publishDate"),
        })
    return sonuc


def is_hafta_ici(d):
    return d.weekday() < 5  # 0=Pazartesi ... 4=Cuma


def gunler_arasi(baslangic, bitis):
    """[baslangic, bitis] arasındaki hafta içi günleri tek tek döner."""
    gun = baslangic
    while gun <= bitis:
        if is_hafta_ici(gun):
            yield gun
        gun += timedelta(days=1)


def gecmis_6_ayi_tara(session):
    """İlk çalıştırma: geçmiş 6 ayın raporlarının, YAYINLANDIKLARI ayın 1-10'u
    aralığındaki HER İŞ GÜNÜNÜ ayrı ayrı tarar (her rapor bir önceki ay için olur).
    Not: 10 günü tek seferde sorgulamak API'nin 2000 sonuç sınırına takılıp fon
    bildirimlerine hiç ulaşamıyordu — bu yüzden günlük, dar pencerelerle tarıyoruz."""
    print("İlk çalıştırma tespit edildi — geçmiş 6 ay taranıyor...")
    bugun = date.today()
    tum_kayitlar = []
    yil, ay = bugun.year, bugun.month
    for _ in range(6):
        pencere_baslangic = date(yil, ay, 1)
        pencere_bitis = min(date(yil, ay, 10), bugun)
        if pencere_bitis >= pencere_baslangic:
            for gun in gunler_arasi(pencere_baslangic, pencere_bitis):
                print(f"  Taranıyor: {gun}")
                bildirimler = fetch_window(session, gun, gun)
                tum_kayitlar.extend(extract_portfoy_raporlari(bildirimler))
                time.sleep(1)
        ay -= 1
        if ay == 0:
            ay = 12
            yil -= 1
    return tum_kayitlar


def bu_ayi_tara(session):
    """Günlük çalışma: sadece bugün ayın 1-10'u arasındaysa, ayın başından bugüne
    kadarki her iş gününü tek tek tarar. 11'den sonra hiç istek atmaz."""
    bugun = date.today()
    if bugun.day > 10:
        print(f"Bugün ayın {bugun.day}. günü — 10'dan sonra yeni yükleme olmadığı için taranmadı.")
        return []
    pencere_baslangic = date(bugun.year, bugun.month, 1)
    tum_kayitlar = []
    for gun in gunler_arasi(pencere_baslangic, bugun):
        print(f"  Taranıyor: {gun}")
        bildirimler = fetch_window(session, gun, gun)
        tum_kayitlar.extend(extract_portfoy_raporlari(bildirimler))
        time.sleep(1)
    return tum_kayitlar


def main():
    import os
    session = requests.Session()
    _warmup_session(session)

    if os.path.exists(OUT_PATH):
        mevcut = pd.read_parquet(OUT_PATH)
        yeni_kayitlar = bu_ayi_tara(session)
    else:
        mevcut = pd.DataFrame(columns=["Fon Kodu", "Yil", "Ay", "disclosureIndex", "publishDate"])
        yeni_kayitlar = gecmis_6_ayi_tara(session)

    if not yeni_kayitlar:
        print(f"Yeni kayıt bulunamadı. Toplam mevcut kayıt: {len(mevcut)}")
        if mevcut.empty:
            return
    else:
        yeni_df = pd.DataFrame(yeni_kayitlar)
        birlesik = pd.concat([mevcut, yeni_df], ignore_index=True)
        # Aynı (Fon Kodu, Yıl, Ay) için en son gelen kaydı tut (düzeltme/tekrar olabilir)
        birlesik = birlesik.drop_duplicates(subset=["Fon Kodu", "Yil", "Ay"], keep="last")
        mevcut = birlesik

    # Her fon için sadece en güncel KEEP_MONTHS ayı tut
    mevcut = mevcut.sort_values(["Fon Kodu", "Yil", "Ay"])
    mevcut = mevcut.groupby("Fon Kodu", group_keys=False).tail(KEEP_MONTHS)

    mevcut.to_parquet(OUT_PATH, index=False)
    print(f"✅ {len(mevcut)} kayıt, {mevcut['Fon Kodu'].nunique()} fon için kaydedildi -> {OUT_PATH}")


if __name__ == "__main__":
    main()
