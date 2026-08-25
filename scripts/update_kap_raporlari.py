"""
Her TEFAS fonu için aylık "Portföy Dağılım Raporu" bildirimlerinin KAP bildirim
numarasını (disclosureIndex) toplar.

Kaynak: https://api.dagilimraporu.com/history/{yil}/{ay} — bu, KAP'ın (Kamuyu
Aydınlatma Platformu) kendi resmi API'sinden veri sunan üçüncü taraf bir site.
KAP'ın kendi resmi API'sini (www.kap.org.tr/tr/api/disclosure/members/byCriteria)
doğrudan kullanmayı denedik, ama o uç nokta güvenlik duvarının JavaScript
çalıştırılmasını gerektiren bir doğrulama (bot koruması) istiyor — basit bir
Python isteğiyle bu çerezler alınamıyor. dagilimraporu.com'un kendi API'si bu
sorunu taşımıyor ve aynı veriyi (fundCode, disclosureIndex vb.) sunuyor.

Önemli not: bu, dagilimraporu.com'un genel kullanıcılarına değil, kendi iç
API'sine (resmi olarak dokümante edilmemiş) erişmek demektir — bilerek kabul
edilen bir risk. Kullanıcı sayımızdan bağımsız, günde sadece 1-6 istek atarak
(ayda bir kez, sadece ayın 1-10'unda) bu siteye asgari yük bindiriyoruz.

Neden böyle çalışır:
- Portföy yönetim şirketleri, bir önceki ayın dağılım raporunu HER AYIN
  1-10'u arasında KAP'a yüklüyor; 10'undan sonra yeni yükleme olmuyor.
- Dosya hiç yoksa (ilk çalıştırma) geçmiş 6 ayı tek tek tarayıp doldurur.
  Dosya zaten varsa, sadece bugün ayın 1-10'u arasındaysa bu ayın (henüz
  gelmiş olabilecek) raporunu arar; 11'inden sonra hiç istek atmadan çıkar.
"""
import requests
import pandas as pd
import time
import os
from datetime import date

OUT_PATH = "kap_raporlari.parquet"
API_URL = "https://api.dagilimraporu.com/history/{yil}/{ay}"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://dagilimraporu.com/",
}
KEEP_MONTHS = 6  # her fon için en fazla saklanacak ay sayısı


def fetch_month(yayin_yili, yayin_ayi, deneme=3):
    """{yayin_yili}/{yayin_ayi} içinde yayınlanmış tüm KAP bildirimlerini döner
    (fon dışı bildirimler dahil olabilir — çağıran taraf filtrelemeli)."""
    url = API_URL.format(yil=yayin_yili, ay=f"{yayin_ayi:02d}")
    params = {"v": 2, "fresh": 1, "t": int(time.time() * 1000)}
    for i in range(1, deneme + 1):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"  Deneme {i}/{deneme} başarısız ({yayin_yili}/{yayin_ayi:02d}): {e}")
            time.sleep(3)
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


def gecmis_6_ayi_tara():
    """İlk çalıştırma: geçmiş 6 "yayın ayı"nı (bugünkü ay dahil, geriye doğru)
    tek tek tarar — her biri bir önceki ayın raporunu içerir."""
    print("İlk çalıştırma tespit edildi — geçmiş 6 ay taranıyor...")
    bugun = date.today()
    tum_kayitlar = []
    yil, ay = bugun.year, bugun.month
    for _ in range(6):
        print(f"  Taranıyor: {yil}-{ay:02d}")
        bildirimler = fetch_month(yil, ay)
        print(f"    Toplam bildirim: {len(bildirimler)}")
        tum_kayitlar.extend(extract_portfoy_raporlari(bildirimler))
        time.sleep(1)
        ay -= 1
        if ay == 0:
            ay = 12
            yil -= 1
    return tum_kayitlar


def bu_ayi_tara():
    """Günlük çalışma: sadece bugün ayın 1-10'u arasındaysa, bu ayı tarar.
    11'den sonra hiç istek atmaz."""
    bugun = date.today()
    if bugun.day > 10:
        print(f"Bugün ayın {bugun.day}. günü — 10'dan sonra yeni yükleme olmadığı için taranmadı.")
        return []
    print(f"Taranıyor: {bugun.year}-{bugun.month:02d}")
    bildirimler = fetch_month(bugun.year, bugun.month)
    print(f"  Toplam bildirim: {len(bildirimler)}")
    return extract_portfoy_raporlari(bildirimler)


def main():
    if os.path.exists(OUT_PATH):
        mevcut = pd.read_parquet(OUT_PATH)
        yeni_kayitlar = bu_ayi_tara()
    else:
        mevcut = pd.DataFrame(columns=["Fon Kodu", "Yil", "Ay", "disclosureIndex", "publishDate"])
        yeni_kayitlar = gecmis_6_ayi_tara()

    if not yeni_kayitlar:
        print(f"Yeni kayıt bulunamadı. Toplam mevcut kayıt: {len(mevcut)}")
        if mevcut.empty:
            return
    else:
        yeni_df = pd.DataFrame(yeni_kayitlar)
        birlesik = pd.concat([mevcut, yeni_df], ignore_index=True)
        birlesik = birlesik.drop_duplicates(subset=["Fon Kodu", "Yil", "Ay"], keep="last")
        mevcut = birlesik

    mevcut = mevcut.sort_values(["Fon Kodu", "Yil", "Ay"])
    mevcut = mevcut.groupby("Fon Kodu", group_keys=False).tail(KEEP_MONTHS)

    mevcut.to_parquet(OUT_PATH, index=False)
    print(f"✅ {len(mevcut)} kayıt, {mevcut['Fon Kodu'].nunique()} fon için kaydedildi -> {OUT_PATH}")


if __name__ == "__main__":
    main()
