from playwright.sync_api import sync_playwright

URL = "https://www.tefas.gov.tr/tr/fon-verileri?fundType=YAT&view=portfolioDistribution"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1200})
    print("Sayfaya gidiliyor...")
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)  # SPA'nın veriyi çekip render etmesi için ek süre

    title = page.title()
    print("Sayfa başlığı:", title)

    text_len = len(page.inner_text("body"))
    print("Sayfa metin uzunluğu:", text_len)

    page.screenshot(path="deneme_ekran_goruntusu.png", full_page=True)
    print("Ekran görüntüsü kaydedildi: deneme_ekran_goruntusu.png")

    # İlk 3000 karakteri de yazdıralım, tablo var mı diye bakalım
    print("--- SAYFA METNİ (ilk 3000 karakter) ---")
    print(page.inner_text("body")[:3000])

    browser.close()
