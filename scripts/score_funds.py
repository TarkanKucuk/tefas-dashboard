import pandas as pd
import numpy as np
import os

# ============================================================
# BU SATIRI ELLE GÜNCELLE: TLREF (Borsa İstanbul TL Referans Faiz Oranı)
# https://www.borsaistanbul.com/endeksler/tlref adresinden en son değeri al
RISK_FREE_RATE = 0.3999  # 17 Temmuz 2026 itibarıyla %39,99

# "Hareketler" ve "Puanlama - Kategori Özeti" sayfalarında gösterilen uyarı:
# bu iki sayfanın hesaplamaları yalnızca TEFAS'a açık fonları baz alır.
ACIK_FON_UYARISI = (
    '<div style="background:rgba(120,140,180,0.12); border:1px solid var(--line); '
    'border-radius:8px; padding:10px 14px; margin-bottom:16px; color:var(--ink-dim); font-size:13px;">'
    "ℹ️ Bu sayfadaki hesaplamalar yalnızca TEFAS'a açık (alım-satıma açık) fonları baz alır."
    '</div>'
)

# Portföyüm ve Favorilerim sayfalarında ORTAK kullanılan Sharpe optimizasyonu JS
# mantığı — kod tekrarını önlemek için tek yerde tanımlanıp iki sayfaya da f-string
# içinde {SHARPE_OPT_JS} olarak enjekte edilir. Bu DÜZ bir string (f-string DEĞİL),
# bu yüzden içindeki { } karakterleri kaçışsız, olduğu gibi kalır.
SHARPE_OPT_JS = '''
/* ---------- Sharpe Optimizasyonu ---------- */

function gunlukGetiriSerisi(fiyatGrafigi) {
    // Basit ardışık-nokta getirisi (pct_change) — score_funds.py'nin resmi
    // Sharpe_1Y hesabıyla BİREBİR aynı yöntem. Önceden buradaki "gün farkına
    // göre normalize etme" mantığı, normal hafta sonu/tatil boşluklarını
    // (Cuma→Pazartesi gibi, her fonda her hafta olan gayet normal bir durum)
    // yanlışlıkla "seyreltilmiş veri" sayıp getiriyi günlere bölüyordu — bu,
    // volatiliteyi yapay olarak çok küçültüp Sharpe'ı anlamsız uç değerlere
    // (örn. BGP için -39) savuruyordu. Basit fark, doğru ve script'le tutarlı.
    if (!fiyatGrafigi || fiyatGrafigi.length < 2) return [];
    const sonuc = [];
    for (let i = 1; i < fiyatGrafigi.length; i++) {
        const onceki = fiyatGrafigi[i - 1], simdi = fiyatGrafigi[i];
        if (!(onceki.value > 0) || !(simdi.value > 0)) continue;
        sonuc.push({ date: simdi.time, getiri: simdi.value / onceki.value - 1 });
    }
    return sonuc;
}

function ortakTarihleriBul(serilerObj) {
    const kodlar = Object.keys(serilerObj);
    if (!kodlar.length) return [];
    let ortak = new Set(serilerObj[kodlar[0]].map(x => x.date));
    for (let i = 1; i < kodlar.length; i++) {
        const buSeri = new Set(serilerObj[kodlar[i]].map(x => x.date));
        ortak = new Set([...ortak].filter(t => buSeri.has(t)));
    }
    return [...ortak].sort();
}

function ortalama(arr) { return arr.reduce((a, b) => a + b, 0) / arr.length; }

function kovaryansHesapla(a, b) {
    const ma = ortalama(a), mb = ortalama(b);
    let toplam = 0;
    for (let i = 0; i < a.length; i++) toplam += (a[i] - ma) * (b[i] - mb);
    return toplam / Math.max(1, a.length - 1);
}

function portfoyGetiriVeRisk(agirliklar, ortGetiriler, kovMatris) {
    const n = agirliklar.length;
    let getiri = 0;
    for (let i = 0; i < n; i++) getiri += agirliklar[i] * ortGetiriler[i];
    let varyans = 0;
    for (let i = 0; i < n; i++)
        for (let j = 0; j < n; j++)
            varyans += agirliklar[i] * agirliklar[j] * kovMatris[i][j];
    return { getiri, risk: Math.sqrt(Math.max(0, varyans)) };
}

function yillikSharpe(gunlukGetiri, gunlukRisk, gunlukRiskFree) {
    if (!(gunlukRisk > 0)) return null;
    // Bileşik (geometrik) yıllıklandırma — score_funds.py'nin resmi Sharpe_1Y
    // hesaplamasıyla (ann_return = (1+ort)^252 - 1) birebir aynı yöntem.
    const yillikGetiri = Math.pow(1 + gunlukGetiri, 252) - 1;
    const yillikRisk = gunlukRisk * Math.sqrt(252);
    const yillikRiskFree = Math.pow(1 + gunlukRiskFree, 252) - 1;
    return (yillikGetiri - yillikRiskFree) / yillikRisk;
}

function rastgeleAgirlikUret(n, minA, maxA) {
    for (let deneme = 0; deneme < 5000; deneme++) {
        const ham = Array.from({ length: n }, () => Math.random());
        const toplam = ham.reduce((a, b) => a + b, 0);
        const agirliklar = ham.map(x => x / toplam);
        if (agirliklar.every(w => w >= minA - 1e-9 && w <= maxA + 1e-9)) return agirliklar;
    }
    return null;
}

function monteCarloOptimize(ortGetiriler, kovMatris, minA, maxA, gunlukRiskFree, denemeSayisi) {
    const n = ortGetiriler.length;
    let enIyiAgirlik = null, enIyiSharpe = -Infinity;
    let basarili = 0;
    for (let i = 0; i < denemeSayisi; i++) {
        const agirliklar = rastgeleAgirlikUret(n, minA, maxA);
        if (!agirliklar) continue;
        basarili++;
        const { getiri, risk } = portfoyGetiriVeRisk(agirliklar, ortGetiriler, kovMatris);
        const sharpe = yillikSharpe(getiri, risk, gunlukRiskFree);
        if (sharpe != null && sharpe > enIyiSharpe) {
            enIyiSharpe = sharpe;
            enIyiAgirlik = agirliklar;
        }
    }
    return { agirliklar: enIyiAgirlik, sharpe: enIyiAgirlik ? enIyiSharpe : null, basarili };
}

/**
 * Ortak optimizasyon çalıştırıcı. `kodlar`: fon kod listesi (fundsData'da mevcut
 * olmalı). `mevcutAgirliklar`: {kod: agirlik(0-1)} — Portföyüm için gerçek pay
 * bazlı ağırlıklar, Favoriler için eşit ağırlık (1/N) varsayımı geçirilir.
 * `sonucElementIdleri`: {durum, sonuc, mevcutSharpe, onerilenSharpe, tablo} DOM id'leri.
 */
function sharpeOptimizasyonuCalistir(kodlar, mevcutAgirliklar, minInputId, maxInputId, elementIdleri) {
    const durumEl = document.getElementById(elementIdleri.durum);
    const sonucEl = document.getElementById(elementIdleri.sonuc);
    sonucEl.style.display = 'none';
    durumEl.textContent = '';

    const gecerliKodlar = kodlar.filter(k => fundsData[k] && fundsData[k].fiyat_grafigi && fundsData[k].fiyat_grafigi.length > 1);
    if (gecerliKodlar.length < 2) {
        durumEl.textContent = 'Optimizasyon için en az 2 fon (fiyat verisi olan) gerekiyor.';
        return;
    }

    const minA = (parseFloat(document.getElementById(minInputId).value) || 0) / 100;
    const maxA = (parseFloat(document.getElementById(maxInputId).value) || 100) / 100;
    if (minA > maxA) {
        durumEl.textContent = 'Min. ağırlık, Max. ağırlıktan büyük olamaz.';
        return;
    }
    const n = gecerliKodlar.length;
    if (minA * n > 1 + 1e-9 || maxA * n < 1 - 1e-9) {
        durumEl.textContent = `Girilen Min/Max ağırlıklarla ${n} fonun toplamı %100 olacak bir dağılım matematiksel olarak mümkün değil.`;
        return;
    }

    const serilerObj = {};
    gecerliKodlar.forEach(k => { serilerObj[k] = gunlukGetiriSerisi(fundsData[k].fiyat_grafigi); });
    const ortakTarihler = ortakTarihleriBul(serilerObj);
    if (ortakTarihler.length < 30) {
        durumEl.textContent = `Fonlar arasında yeterli ortak veri yok (sadece ${ortakTarihler.length} gün) — en az 30 gün gerekiyor.`;
        return;
    }

    const getiriMatrisi = {};
    gecerliKodlar.forEach(k => {
        const harita = {};
        serilerObj[k].forEach(x => { harita[x.date] = x.getiri; });
        getiriMatrisi[k] = ortakTarihler.map(t => harita[t]);
    });
    const ortGetiriler = gecerliKodlar.map(k => ortalama(getiriMatrisi[k]));
    const kovMatris = gecerliKodlar.map(ki => gecerliKodlar.map(kj => kovaryansHesapla(getiriMatrisi[ki], getiriMatrisi[kj])));
    const gunlukRiskFree = Math.pow(1 + RISK_FREE_RATE_YILLIK, 1 / 252) - 1;

    const sonuc = monteCarloOptimize(ortGetiriler, kovMatris, minA, maxA, gunlukRiskFree, 20000);
    if (!sonuc.agirliklar) {
        durumEl.textContent = 'Girilen kısıtlara uyan bir ağırlık dağılımı bulunamadı — Min/Max aralığını genişletmeyi deneyin.';
        return;
    }

    // Mevcut (gerçek ya da eşit varsayımlı) ağırlıklarla mevcut Sharpe'ı hesapla
    const mevcutVektor = gecerliKodlar.map(k => mevcutAgirliklar[k] || 0);
    const mevcutToplam = mevcutVektor.reduce((a, b) => a + b, 0);
    const mevcutNormalize = mevcutToplam > 0 ? mevcutVektor.map(w => w / mevcutToplam) : gecerliKodlar.map(() => 1 / n);
    const mevcutSonuc = portfoyGetiriVeRisk(mevcutNormalize, ortGetiriler, kovMatris);
    const mevcutSharpe = yillikSharpe(mevcutSonuc.getiri, mevcutSonuc.risk, gunlukRiskFree);

    document.getElementById(elementIdleri.mevcutSharpe).textContent = mevcutSharpe != null ? mevcutSharpe.toFixed(2) : '—';
    document.getElementById(elementIdleri.onerilenSharpe).textContent = sonuc.sharpe.toFixed(2);

    // Her fonun KENDİ Sharpe oranı — kullanıcı geri bildirimiyle düzeltildi:
    // BUNU portföydeki fonların ORTAK (kesişen) tarih penceresinden DEĞİL, o
    // fonun KENDİ TAM geçmişinden (en fazla son ~252 iş günü, yani ~1 yıl;
    // daha kısa geçmişi varsa elindeki kadarıyla) hesaplıyoruz. Aksi halde,
    // portföydeki en kısa ömürlü fon, TÜM fonların Sharpe'ını kendi kısa
    // penceresine hapsedip yanlış/yanıltıcı sonuçlar üretiyordu.
    const kendiSharpeler = gecerliKodlar.map(k => {
        const tamSeri = serilerObj[k].map(x => x.getiri).slice(-252);
        // Eşik: score_funds.py'nin resmi Sharpe_1Y hesabı, son 1 yıllık
        // penceredeki gözlem sayısının en az 100 olmasını şart koşuyor
        // (len(daily_rets) >= 100) — aynı eşiği burada da uyguluyoruz.
        if (tamSeri.length < 100) return null;
        const kendiOrt = ortalama(tamSeri);
        const kendiRisk = Math.sqrt(tamSeri.reduce((s, x) => s + (x - kendiOrt) ** 2, 0) / Math.max(1, tamSeri.length - 1));
        return yillikSharpe(kendiOrt, kendiRisk, gunlukRiskFree);
    });

    let satirlar = gecerliKodlar.map((k, i) => ({
        kod: k,
        kendiSharpe: kendiSharpeler[i],
        mevcut: mevcutNormalize[i] * 100,
        onerilen: sonuc.agirliklar[i] * 100,
    }));
    satirlar.sort((a, b) => b.onerilen - a.onerilen);
    const mevcutBaslik = elementIdleri.mevcutEtiket || 'Mevcut Ağırlık';
    const tabloHtml = '<tr><th>Kod</th><th>Fonun Sharpe Rasyosu</th><th style="text-align:right;">' + mevcutBaslik + '</th><th style="text-align:right;">Önerilen Ağırlık</th></tr>' +
        satirlar.map(s => '<tr><td><a href="fon-karti.html?kod=' + s.kod + '">' + s.kod + '</a></td>' +
            '<td>' + (s.kendiSharpe != null ? s.kendiSharpe.toFixed(2) : '—') + '</td>' +
            '<td style="text-align:right;">' + s.mevcut.toFixed(1) + '%</td>' +
            '<td style="text-align:right;"><strong>' + s.onerilen.toFixed(1) + '%</strong></td></tr>').join('');
    document.getElementById(elementIdleri.tablo).innerHTML = tabloHtml;

    durumEl.textContent = '';
    sonucEl.style.display = 'block';
}

'''
# ============================================================

DATA_PATH = "tefas_gecmis_veri.parquet"
MAPPING_PATH = "fon_kategori_eslestirme.xlsx"

WEIGHTS = {
    'Skor_Momentum': 0.35,
    'Skor_Getiri': 0.25,
    'Skor_ParaAkışı': 0.15,
    'Skor_Sharpe': 0.15,
    'Skor_StdDev': 0.10,
}
RETURN_SUBWEIGHTS = {'Getiri_3A_%': 0.20, 'Getiri_6A_%': 0.35, 'Getiri_1Y_%': 0.45}
LABEL_MAP = {'Skor_Momentum': 'Momentum', 'Skor_Getiri': 'Getiri',
             'Skor_ParaAkışı': 'ParaAkışı', 'Skor_Sharpe': 'Sharpe', 'Skor_StdDev': 'StdDev'}

NAV_PAGES = [
    ('index.html', 'Hareketler'),
    ('favoriler.html', '★ Favorilerim'),
    ('portfoyum.html', '💼 Portföyüm'),
    ('kategori-ozeti.html', 'Puanlama - Kategori Özeti'),
    ('yeni-fonlar.html', 'En Son Eklenen Fonlar'),
]

BASE_STYLE = """
:root {
    --bg: #23252d;
    --panel: #2c2f39;
    --card: #12141a;
    --ink: #eef0f4;
    --ink-dim: #9aa0ac;
    --line: #3a3d48;
    --teal: #2f7c7a;
    --teal-bright: #3fb6ab;
    --green: #4cbb6d;
    --red: #e05a5a;
    --blue: #4a7fe0;
}
* { box-sizing: border-box; }
body {
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    margin: 0; padding: 32px 40px 60px; background: var(--bg); color: var(--ink);
}
.header {
    background: linear-gradient(135deg, #1a3a5c 0%, #2f7c7a 100%);
    color: white; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.35);
}
.header h1 { margin: 0; font-size: 26px; font-weight: 600; }
.header .meta { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
.header .meta span { font-size: 13px; white-space: nowrap; opacity: 0.9; }
.header .meta span:not(:last-child) { border-right: 1px solid rgba(255,255,255,0.25); padding-right: 16px; }
.nav-bar { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.nav-bar a { color: white; text-decoration: none; padding: 5px 14px; border-radius: 20px; font-size: 13px; white-space: nowrap; }
@media (max-width: 640px) {
    body { padding: 14px 12px 40px; }
    .header { padding: 14px 16px; margin-bottom: 14px; }
    .header h1 { font-size: 17px; line-height: 1.3; }
    .header h1 span { display: block; font-size: 12px; margin-top: 2px; }
    .header img { height: 28px !important; width: 28px !important; }
    .header .meta { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 2px; }
    .nav-bar { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 8px; padding-bottom: 2px; }
    .card { padding: 12px 12px 16px; }
}
.card {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 20px 24px 24px; margin-bottom: 18px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.25);
}
.kat-card h2 { margin: 0 0 4px 0; color: var(--teal-bright); font-size: 18px; }
.kat-count { color: var(--ink-dim); font-size: 13px; font-weight: 400; }
.kat-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 800px) { .kat-cols { grid-template-columns: 1fr; } }
h3 { font-size: 13px; margin: 0 0 8px 0; color: var(--ink); }
h3.up { color: var(--green); }
h3.down { color: var(--red); }
table.mini { width: 100%; border-collapse: collapse; font-size: 13px; }
table.mini th { text-align: left; color: var(--ink-dim); font-weight: 500; padding: 4px 6px; border-bottom: 1px solid var(--line); }
table.mini td { padding: 5px 6px; border-bottom: 1px solid #1c1e26; color: var(--ink); }
table.mini td a { color: var(--teal-bright); font-weight: 600; text-decoration: underline; text-decoration-color: #3a6b68; }
table.mini td a:hover { color: #6fd8cd; text-decoration-color: #6fd8cd; }
.score-badge { display: inline-block; min-width: 50px; padding: 2px 7px; border-radius: 6px; font-weight: 600; text-align: center; }
.score-badge.good { background: rgba(76,187,109,0.18); color: var(--green); }
.score-badge.bad { background: rgba(224,90,90,0.18); color: var(--red); }
.period-tabs { display: flex; gap: 6px; margin-bottom: 18px; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 2px; }
.period-tab {
    padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
    background: var(--panel); color: var(--ink-dim); border: 1px solid var(--line); white-space: nowrap; flex-shrink: 0;
}
.period-tab.active { background: var(--blue); color: white; border-color: var(--blue); }
.period-panel { display: none; }
.period-panel.active { display: block; }
footer { text-align: center; color: var(--ink-dim); font-size: 12px; margin-top: 24px; }
.pos { color: var(--green); font-weight: 600; }
.neg { color: var(--red); font-weight: 600; }
"""


def fonlarca_link(kod):
    return f'<a href="fon-karti.html?kod={kod}" target="_blank">{kod}</a>'
def kisalt_unvan(ad):
    """Fon unvanındaki uzun parantez içi ifadeleri kısaltır (sadece görüntüleme
    amaçlı — kaynak veriyi değiştirmez). Örn: '... (HİSSE SENEDİ YOĞUN FON)'
    -> '... (HSYF)'."""
    if not ad:
        return ad
    return ad.replace("(HİSSE SENEDİ YOĞUN FON)", "(HSYF)")


def load_fon_adlari():
    """Fon adlarını TEFAS'ın kendi 'Fon Unvanı' verisinden (tefas_portfoy_dagilim.parquet)
    okur — manuel eşleştirme dosyasına (fon_kategori_eslestirme.xlsx) bağımlı kalmasın diye.
    O dosya sadece Alt Kategori (kendi sınıflandırmamız) için hâlâ gerekli."""
    path = "tefas_portfoy_dagilim.parquet"
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_parquet(path, columns=["Fon Kodu", "Fon Unvanı", "Tarih"])
    except Exception:
        return {}
    df = df.dropna(subset=["Fon Unvanı"]).sort_values("Tarih")
    if df.empty:
        return {}
    return df.groupby("Fon Kodu")["Fon Unvanı"].last().to_dict()


def load_acik_fon_kodlari():
    """TEFAS'a açık (getFplFonList'te yer alan) fon kodlarının kümesini döner.
    Dosya yoksa/boşsa None döner — bu durumda çağıran taraf hiçbir filtre
    uygulamamalı (veri henüz toplanmamışsa 'En Son Eklenen Fonlar' boşalmasın)."""
    path = "tefas_acik_fonlar.parquet"
    if not os.path.exists(path):
        print(f"[acik_fon] {path} bulunamadı, filtre uygulanmayacak.")
        return None
    try:
        df = pd.read_parquet(path, columns=["Fon Kodu"])
    except Exception as e:
        print(f"[acik_fon] {path} okunamadı ({e}), filtre uygulanmayacak.")
        return None
    if df.empty:
        print(f"[acik_fon] {path} boş, filtre uygulanmayacak.")
        return None
    kodlar = set(df["Fon Kodu"])
    print(f"[acik_fon] {len(kodlar)} açık fon kodu yüklendi. KSP içeriyor mu: {'KSP' in kodlar}")
    return kodlar

def nav_bar(active):
    parts = []
    for href, label in NAV_PAGES:
        style = ("background:rgba(255,255,255,0.28); font-weight:600;" if href == active
                 else "background:rgba(255,255,255,0.12);")
        parts.append(f'<a href="{href}" style="{style}">{label}</a>')
    return '<div class="nav-bar">' + ''.join(parts) + '</div>'


def page_header(active, subtitle, anchor, extra_meta=""):
    return f"""<div class="header">
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px; flex-wrap:wrap;">
        <img src="logo.jpg" alt="Fonlarca" style="height:36px; width:36px; border-radius:8px; object-fit:cover;">
        <h1>FONLARCA <span style="font-weight:400; opacity:0.75; font-size:16px;">— {subtitle}</span></h1>
        <div class="fund-search-wrap">
            <input type="text" id="fundSearchInput" list="fundSearchList" placeholder="🔍 Fon ara (kod veya isim)…" autocomplete="off">
            <datalist id="fundSearchList"></datalist>
        </div>
    </div>
    <div class="meta"><span>Son güncelleme: {anchor.date()}</span>{extra_meta}</div>
    {nav_bar(active)}
</div>"""


FUND_SEARCH_STYLE = """
.fund-search-wrap { margin-left: auto; flex: 1; min-width: 200px; max-width: 340px; }
.fund-search-wrap input {
    width: 100%; background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3);
    color: white; border-radius: 8px; padding: 8px 12px; font-size: 13px;
}
.fund-search-wrap input::placeholder { color: rgba(255,255,255,0.7); }
@media (max-width: 640px) {
    .fund-search-wrap { margin-left: 0; max-width: none; width: 100%; }
}
"""

FUND_SEARCH_SCRIPT = """
<script>
(function() {
    var input = document.getElementById('fundSearchInput');
    var list = document.getElementById('fundSearchList');
    if (!input || !list) return;
    var funds = [];
    fetch('data/fon-kartlari/_index.json')
        .then(function(r) { return r.ok ? r.json() : []; })
        .then(function(data) {
            funds = data || [];
            list.innerHTML = funds.map(function(f) {
                var isaret = (f.acik === false) ? ' 🔴' : '';
                return '<option value="' + f.kod + '">' + f.kod + ' — ' + (f.ad || '') + isaret + '</option>';
            }).join('');
        })
        .catch(function() {});
    function go() {
        var raw = input.value.trim();
        if (!raw) return;
        var kod = raw.split(/[—-]/)[0].replace(/[^A-Za-z]/g, '').toUpperCase();
        var match = funds.find(function(f) { return f.kod.toUpperCase() === kod; });
        if (match) window.location.href = 'fon-karti.html?kod=' + match.kod;
    }
    input.addEventListener('change', go);
    input.addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); go(); } });
})();
</script>"""


def page_shell(title, active, body, extra_style="", extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#12141a">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png">
{extra_head}
<style>{BASE_STYLE}{FUND_SEARCH_STYLE}{extra_style}</style>
</head>
<body>
{body}
{FUND_SEARCH_SCRIPT}
</body>
</html>"""


# ------------------------------------------------------------------
# Puanlama hesapları
# ------------------------------------------------------------------

def pct_rank_within(df, col, ascending=True):
    """Alt Kategori içinde percentile (0-100) hesaplar."""
    out = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby('Alt Kategori').groups.items():
        sub = df.loc[idx, col]
        valid = sub.dropna()
        if len(valid) < 2:
            out.loc[valid.index] = 50.0
            continue
        out.loc[valid.index] = valid.rank(pct=True, ascending=ascending) * 100
    return out


def build_fund_metrics(df):
    anchor = df['Tarih'].max()
    records = []

    for fon_kodu, g in df.groupby('Fon Kodu'):
        g = g.sort_values('Tarih')
        latest = g.iloc[-1]
        first_date = g['Tarih'].iloc[0]
        history_days = (anchor - first_date).days

        rec = {
            'Fon Kodu': fon_kodu,
            'Son Tarih': latest['Tarih'],
            'Veri Geçmişi (gün)': history_days,
            'Fon Toplam Değer': latest['Fon Toplam Değer'],
            'Kişi Sayısı': latest['Kişi Sayısı'],
        }

        # Momentum + Para Akışı (1 ay)
        cutoff = anchor - pd.Timedelta(days=30)
        past = g[g['Tarih'] <= cutoff]
        if not past.empty and past.iloc[-1]['Fiyat'] > 0:
            past_row = past.iloc[-1]
            rec['Getiri_1A_%'] = (latest['Fiyat'] / past_row['Fiyat'] - 1) * 100
            units_start = past_row['Tedavüldeki Pay Sayısı']
            units_end = latest['Tedavüldeki Pay Sayısı']
            if pd.notna(units_start) and units_start != 0:
                rec['Net_Akış_TL'] = (units_end - units_start) * latest['Fiyat']
        else:
            rec['Getiri_1A_%'] = np.nan

        # Getiri dönemleri
        for label, days in [('3A', 90), ('6A', 180), ('1Y', 365)]:
            cutoff = anchor - pd.Timedelta(days=days)
            past = g[g['Tarih'] <= cutoff]
            if not past.empty and past.iloc[-1]['Fiyat'] > 0 and history_days >= days - 15:
                rec[f'Getiri_{label}_%'] = (latest['Fiyat'] / past.iloc[-1]['Fiyat'] - 1) * 100
            else:
                rec[f'Getiri_{label}_%'] = np.nan

        # Sharpe & StdDev (son 1 yıl)
        if history_days >= 300:
            window = g[g['Tarih'] >= (anchor - pd.Timedelta(days=365))].copy()
            window['gunluk_getiri'] = window['Fiyat'].pct_change()
            daily_rets = window['gunluk_getiri'].dropna()
            if len(daily_rets) >= 100:
                ann_return = (1 + daily_rets.mean()) ** 252 - 1
                ann_vol = daily_rets.std() * np.sqrt(252)
                rec['StdDev_1Y_%'] = ann_vol * 100
                rec['Sharpe_1Y'] = (ann_return - RISK_FREE_RATE) / ann_vol if ann_vol > 0 else np.nan

        records.append(rec)

    return pd.DataFrame(records), anchor


def compute_scores(res):
    kat_toplam = res.groupby('Alt Kategori')['Net_Akış_TL'].apply(lambda x: x.abs().sum())
    res['Kategori_Toplam_Akış_Hareketi_TL'] = res['Alt Kategori'].map(kat_toplam)
    res['Fon_Payı_%'] = np.where(
        res['Kategori_Toplam_Akış_Hareketi_TL'] > 0,
        res['Net_Akış_TL'] / res['Kategori_Toplam_Akış_Hareketi_TL'] * 100,
        0.0,
    )

    res['Skor_Momentum'] = pct_rank_within(res, 'Getiri_1A_%', ascending=True)
    res['Skor_ParaAkışı'] = pct_rank_within(res, 'Fon_Payı_%', ascending=True)
    res['Skor_Sharpe'] = pct_rank_within(res, 'Sharpe_1Y', ascending=True)
    res['Skor_StdDev'] = pct_rank_within(res, 'StdDev_1Y_%', ascending=False)

    period_pct = {c: pct_rank_within(res, c, ascending=True) for c in RETURN_SUBWEIGHTS}
    return_scores = []
    for i in res.index:
        available = {c: period_pct[c].loc[i] for c in RETURN_SUBWEIGHTS if not pd.isna(period_pct[c].loc[i])}
        if not available:
            return_scores.append(np.nan)
            continue
        total_w = sum(RETURN_SUBWEIGHTS[c] for c in available)
        weighted_avg = sum(RETURN_SUBWEIGHTS[c] / total_w * v for c, v in available.items())
        penalty = (np.std(list(available.values())) * 0.15) if len(available) >= 2 else 0.0
        return_scores.append(np.clip(weighted_avg - penalty, 0, 100))
    res['Skor_Getiri'] = return_scores

    final_scores, components_used = [], []
    for i in res.index:
        available = {c: res.loc[i, c] for c in WEIGHTS if not pd.isna(res.loc[i, c])}
        if 'Skor_Momentum' not in available:
            final_scores.append(np.nan)
            components_used.append("Yetersiz veri")
            continue
        total_w = sum(WEIGHTS[c] for c in available)
        score = sum(WEIGHTS[c] / total_w * v for c, v in available.items())
        final_scores.append(round(score, 2))
        components_used.append("+".join(LABEL_MAP[c] for c in available))

    res['TEFAS_Skoru'] = final_scores
    res['Kullanılan_Bileşenler'] = components_used
    res['Kategori_Sırası'] = res.groupby('Alt Kategori')['TEFAS_Skoru'].rank(ascending=False, method='min')
    return res


# ------------------------------------------------------------------
# Sayfa 2: Kategori Özeti
# ------------------------------------------------------------------

def write_category_summary(res, anchor):
    plot_df = res[res['TEFAS_Skoru'].notna()]
    sections = []
    kategori_listesi = []
    for kat, g in plot_df.groupby('Alt Kategori', sort=True):
        if len(g) < 3:
            continue
        kategori_listesi.append(kat)
        g_sorted = g.sort_values('TEFAS_Skoru', ascending=False)
        top5 = g_sorted.head(5)
        bottom5 = g_sorted.tail(5).sort_values('TEFAS_Skoru')

        def rows(sub, cls):
            out = ""
            for _, r in sub.iterrows():
                out += (f"<tr><td>{fonlarca_link(r['Fon Kodu'])}</td><td>{kisalt_unvan(r['Fon Adı'])}</td>"
                        f"<td><span class='score-badge {cls}'>{r['TEFAS_Skoru']:.1f}</span></td></tr>")
            return out

        sections.append(f"""
<div class="card kat-card" data-kategori="{kat}">
    <h2>{kat} <span class="kat-count">({len(g)} fon)</span></h2>
    <div class="kat-cols">
        <div>
            <h3 class="up">▲ En İyi 5</h3>
            <table class="mini"><tr><th>Kod</th><th>Fon Adı</th><th>Skor</th></tr>{rows(top5, 'good')}</table>
        </div>
        <div>
            <h3 class="down">▼ En Kötü 5</h3>
            <table class="mini"><tr><th>Kod</th><th>Fon Adı</th><th>Skor</th></tr>{rows(bottom5, 'bad')}</table>
        </div>
    </div>
</div>""")

    kategori_secenekleri = "".join(f'<option value="{k}">{k}</option>' for k in kategori_listesi)
    filtre_kutusu = f"""
<div class="card">
    <label for="kategori-filter" style="color:var(--ink-dim); font-size:13px; margin-right:8px;">Kategori:</label>
    <select id="kategori-filter" style="background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:14px; min-width:220px;">
        <option value="">Tümü</option>
        {kategori_secenekleri}
    </select>
</div>
<script>
document.getElementById('kategori-filter').addEventListener('change', function(){{
    const secili = this.value;
    document.querySelectorAll('.kat-card').forEach(function(kart){{
        kart.style.display = (!secili || kart.dataset.kategori === secili) ? '' : 'none';
    }});
}});
</script>"""

    body = f"""{page_header('kategori-ozeti.html', 'Kategori Özeti', anchor)}
{ACIK_FON_UYARISI}
{filtre_kutusu}
{''.join(sections)}"""

    with open("docs/kategori-ozeti.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA — Kategori Özeti", "kategori-ozeti.html", body))
    print("Kategori özeti oluşturuldu: docs/kategori-ozeti.html")


# ------------------------------------------------------------------
# Sayfa 3: Hareketler (Günlük / Haftalık / Aylık sekmeler) — açılış sayfası
# ------------------------------------------------------------------

def build_movers(df, mapping, days):
    anchor = df['Tarih'].max()
    cutoff = anchor - pd.Timedelta(days=days)
    records = []
    for fon_kodu, g in df.groupby('Fon Kodu'):
        g = g.sort_values('Tarih')
        latest = g.iloc[-1]
        past = g[g['Tarih'] <= cutoff]
        if past.empty:
            continue
        past_row = past.iloc[-1]
        if past_row['Fiyat'] <= 0:
            continue

        rec = {
            'Fon Kodu': fon_kodu,
            'Fiyat_Değişim_%': (latest['Fiyat'] / past_row['Fiyat'] - 1) * 100,
        }

        kisi_start, kisi_end = past_row['Kişi Sayısı'], latest['Kişi Sayısı']
        if pd.notna(kisi_start) and pd.notna(kisi_end):
            rec['Kişi_Değişim'] = kisi_end - kisi_start

        units_start, units_end = past_row['Tedavüldeki Pay Sayısı'], latest['Tedavüldeki Pay Sayısı']
        if pd.notna(units_start) and units_start != 0:
            rec['Net_Akış_TL'] = (units_end - units_start) * latest['Fiyat']

        records.append(rec)

    movers = pd.DataFrame(records)
    movers = movers.merge(mapping[['Fon Kodu', 'Fon Adı', 'Alt Kategori']], on='Fon Kodu', how='left')
    movers = movers[movers['Alt Kategori'].notna()]
    return movers, anchor


def write_hareketler_page(df, mapping):
    import json

    periods = [('gunluk', 1, 'Günlük'), ('haftalik', 7, 'Haftalık'), ('aylik', 30, 'Aylık')]
    movers_by_key = {key: build_movers(df, mapping, days) for key, days, _ in periods}
    anchor = movers_by_key['gunluk'][1]

    def to_records(movers):
        recs = []
        for _, r in movers.iterrows():
            recs.append({
                'kod': r['Fon Kodu'],
                'ad': kisalt_unvan(r['Fon Adı']),
                'kat': r['Alt Kategori'],
                'fiyat': None if pd.isna(r.get('Fiyat_Değişim_%')) else round(float(r['Fiyat_Değişim_%']), 4),
                'kisi': None if pd.isna(r.get('Kişi_Değişim')) else round(float(r['Kişi_Değişim']), 2),
                'akis': None if pd.isna(r.get('Net_Akış_TL')) else round(float(r['Net_Akış_TL']), 2),
            })
        return recs

    movers_json = {key: to_records(movers_by_key[key][0]) for key, _, _ in periods}
    all_categories = sorted(x for x in mapping['Alt Kategori'].dropna().unique())

    data_json = json.dumps(movers_json, ensure_ascii=False)
    categories_json = json.dumps(all_categories, ensure_ascii=False)

    tab_buttons = []
    panels = []
    for i, (key, days, label) in enumerate(periods):
        active_cls = "active" if i == 0 else ""
        tab_buttons.append(f'<button class="period-tab {active_cls}" onclick="showPeriod(\'{key}\')" id="tab-{key}">{label}</button>')
        panels.append(f'<div class="period-panel {active_cls}" id="panel-{key}"></div>')

    category_options = '<option value="">Tüm Kategoriler</option>' + ''.join(
        f'<option value="{k}">{k}</option>' for k in all_categories)

    controls = f"""
<div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:18px;">
    <div class="period-tabs" style="margin-bottom:0;">{''.join(tab_buttons)}</div>
    <div>
        <label for="categorySelect" style="font-size:13px; color:var(--ink-dim); margin-right:8px;">Kategori:</label>
        <select id="categorySelect" onchange="onCategoryChange()">{category_options}</select>
    </div>
</div>"""

    # JS'i düz string olarak kuruyoruz (f-string parantez kaçışından kaçınmak için),
    # sadece veri yer tutucularını yerleştiriyoruz.
    script_js = """
<script>
const MOVERS_DATA = __DATA__;

function fmtPct(v) { return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
function fmtNum(v) { return (v >= 0 ? '+' : '') + Math.round(v).toLocaleString('tr-TR'); }
function fonLink(kod) { return '<a href="fon-karti.html?kod=' + kod + '" target="_blank">' + kod + '</a>'; }

const METRICS = [
    {title: 'Fiyat Hareketleri', key: 'fiyat', fmt: fmtPct, unit: 'Değişim'},
    {title: 'Yatırımcı Sayısı Hareketleri', key: 'kisi', fmt: fmtNum, unit: 'Kişi'},
    {title: 'Para Akışı Hareketleri (TL)', key: 'akis', fmt: fmtNum, unit: 'TL'},
];

function topBottom(data, key) {
    const valid = data.filter(r => r[key] !== null && r[key] !== undefined);
    const desc = [...valid].sort((a, b) => b[key] - a[key]);
    const asc = [...valid].sort((a, b) => a[key] - b[key]);
    return {top5: desc.slice(0, 5), bottom5: asc.slice(0, 5)};
}

function buildRows(list, key, fmt, cls) {
    return list.map(r => '<tr><td>' + fonLink(r.kod) + '</td><td>' + r.ad + '</td>' +
        '<td><span class="score-badge ' + cls + '">' + fmt(r[key]) + '</span></td></tr>').join('');
}

function metricCardHtml(m, data) {
    const bt = topBottom(data, m.key);
    return '<div class="card kat-card"><h2>' + m.title + '</h2><div class="kat-cols">' +
        '<div><h3 class="up">▲ En Çok Artan 5</h3><table class="mini"><tr><th>Kod</th><th>Fon Adı</th><th>' + m.unit + '</th></tr>' +
        buildRows(bt.top5, m.key, m.fmt, 'good') + '</table></div>' +
        '<div><h3 class="down">▼ En Çok Azalan 5</h3><table class="mini"><tr><th>Kod</th><th>Fon Adı</th><th>' + m.unit + '</th></tr>' +
        buildRows(bt.bottom5, m.key, m.fmt, 'bad') + '</table></div></div></div>';
}

function renderPanel(periodKey) {
    const cat = document.getElementById('categorySelect').value;
    let data = MOVERS_DATA[periodKey];
    if (cat) { data = data.filter(r => r.kat === cat); }
    document.getElementById('panel-' + periodKey).innerHTML = METRICS.map(m => metricCardHtml(m, data)).join('');
}

function showPeriod(key) {
    document.querySelectorAll('.period-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.period-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + key).classList.add('active');
    document.getElementById('tab-' + key).classList.add('active');
    renderPanel(key);
}

function onCategoryChange() {
    document.querySelectorAll('.period-panel.active').forEach(p => renderPanel(p.id.replace('panel-', '')));
}

renderPanel('gunluk');
</script>"""
    script_js = script_js.replace("__DATA__", data_json)

    extra_style = """
#categorySelect { border: 1px solid var(--line); border-radius: 6px; padding: 5px 10px; font-size: 13px; background: var(--panel); color: var(--ink); }
#categorySelect option { background: var(--panel); color: var(--ink); }
"""

    body = f"""{page_header('index.html', 'Hareketler', anchor)}
{ACIK_FON_UYARISI}
{controls}
{''.join(panels)}
{script_js}"""

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA — Hareketler", "index.html", body, extra_style))
    print("Hareketler sayfası (açılış sayfası) oluşturuldu: docs/index.html")


# ------------------------------------------------------------------
# Sayfa 4: En Son Eklenen Fonlar
# ------------------------------------------------------------------

def write_yeni_fonlar_page(df, mapping, fon_adlari=None, acik_fon_kodlari=None):
    fon_adlari = fon_adlari or {}
    anchor = df['Tarih'].max()
    cutoff = anchor - pd.Timedelta(days=30)

    first_dates = df.groupby('Fon Kodu')['Tarih'].min().reset_index()
    first_dates.columns = ['Fon Kodu', 'İlk İşlem Tarihi']
    yeni = first_dates[first_dates['İlk İşlem Tarihi'] >= cutoff].copy()
    print(f"[yeni_fonlar] Filtre öncesi (son 30 gün) fon sayısı: {len(yeni)}, "
          f"KSP içeriyor mu: {'KSP' in yeni['Fon Kodu'].values}")
    print(f"[yeni_fonlar] acik_fon_kodlari parametresi: "
          f"{'None (filtre UYGULANMAYACAK)' if acik_fon_kodlari is None else f'{len(acik_fon_kodlari)} kod (filtre uygulanacak)'}")
    # Sadece TEFAS'a açık fonları göster (getFplFonList'ten gelen liste).
    # Liste henüz toplanmadıysa (acik_fon_kodlari None) filtre uygulanmaz.
    if acik_fon_kodlari is not None:
        yeni = yeni[yeni['Fon Kodu'].isin(acik_fon_kodlari)]
    print(f"[yeni_fonlar] Filtre sonrası fon sayısı: {len(yeni)}, "
          f"KSP içeriyor mu: {'KSP' in yeni['Fon Kodu'].values}")
    yeni = yeni.merge(mapping[['Fon Kodu', 'Fon Adı', 'Alt Kategori']], on='Fon Kodu', how='left')
    # Eşleştirme dosyasında hiç olmayan fonlar için de, TEFAS'ın kendi
    # unvanından ismi doldur — sadece Alt Kategori (manuel sınıflandırma) boş kalsın.
    yeni['Fon Adı'] = yeni['Fon Adı'].fillna(yeni['Fon Kodu'].map(fon_adlari))
    yeni = yeni.sort_values('İlk İşlem Tarihi', ascending=False)

    rows = ""
    for _, r in yeni.iterrows():
        # Alt Kategori (manuel eşleştirme) boşsa, fon TEFAS'ta yeni açılmış ve
        # henüz eşleştirme dosyasına eklenmemiş demektir — o sütun boş kalır
        # (kullanıcı için "eşleştirme dosyasını güncellemen lazım" sinyali).
        ad = kisalt_unvan(r['Fon Adı']) if pd.notna(r['Fon Adı']) else ''
        kat = r['Alt Kategori'] if pd.notna(r['Alt Kategori']) else ''
        rows += (f"<tr><td>{fonlarca_link(r['Fon Kodu'])}</td><td>{ad}</td>"
                 f"<td>{kat}</td><td>{r['İlk İşlem Tarihi'].date()}</td></tr>")

    table_html = f"""<table class="mini" style="font-size:14px;">
<tr><th>Kod</th><th>Fon Adı</th><th>Alt Kategori</th><th>İlk İşlem Tarihi</th></tr>
{rows if rows else '<tr><td colspan="4" style="color:var(--ink-dim); padding:16px;">Son 30 günde yeni eklenen fon bulunamadı.</td></tr>'}
</table>"""

    body = f"""{page_header('yeni-fonlar.html', 'En Son Eklenen Fonlar', anchor)}
<div class="card">
    <h2 style="color:var(--teal-bright); margin-top:0;">Son 30 Günde TEFAS'a Açılan Fonlar <span class="kat-count">({len(yeni)} fon)</span></h2>
    {table_html}
</div>"""

    with open("docs/yeni-fonlar.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA — En Son Eklenen Fonlar", "yeni-fonlar.html", body))
    print("En Son Eklenen Fonlar sayfası oluşturuldu: docs/yeni-fonlar.html")


# ------------------------------------------------------------------
# Sayfa 5: Favorilerim (cihaz-lokali, localStorage — sunucu tarafında veri yok)
# ------------------------------------------------------------------

def write_favoriler_page(anchor):
    body = f"""{page_header('favoriler.html', 'Favorilerim', anchor)}

<div class="card">
    <h2 style="color:var(--teal-bright); margin-top:0;">★ Favorilerim</h2>
    <div id="fav-empty" style="display:none; color:var(--ink-dim); padding:16px 0;">
        Henüz favori fon eklemediniz. Bir fon kartında ☆ butonuna basarak ekleyebilirsiniz.
    </div>
    <div id="fav-body" style="display:none;">
        <div class="mini-table-wrap" style="overflow-x:auto;">
            <table class="mini fav-table" id="fav-returns-table" style="font-size:13px;"></table>
        </div>
    </div>
</div>

<div id="fav-charts" style="display:none;">
    <div class="card">
        <div class="period-tabs" id="fav-period-tabs">
            <button class="period-tab active" data-p="Günlük">Günlük</button>
            <button class="period-tab" data-p="Haftalık">Haftalık</button>
            <button class="period-tab" data-p="Aylık">Aylık</button>
            <button class="period-tab" data-p="3 Aylık">3 Aylık</button>
            <button class="period-tab" data-p="6 Aylık">6 Aylık</button>
            <button class="period-tab" data-p="YBB">YBB</button>
            <button class="period-tab" data-p="Yıllık">Yıllık</button>
        </div>
    </div>
    <div class="card">
        <h3 style="color:var(--ink);">Nakit Giriş/Çıkış (Net TL)</h3>
        <div style="height:240px;"><canvas id="fav-cashflow-chart"></canvas></div>
    </div>
    <div class="card">
        <h3 style="color:var(--ink);">Yatırımcı Sayısı Değişimi (Adet)</h3>
        <div style="height:240px;"><canvas id="fav-investor-chart"></canvas></div>
    </div>

    <div class="card">
        <h3 style="color:var(--ink); margin-top:0; font-size:20px;">🎯 Fon Dağılım Optimizasyonu</h3>
        <p style="color:var(--ink-dim); font-size:14px; margin-top:-2px;">
            Elinizdeki fonları hangi oranlarda tutarsanız, geçmiş verilere göre daha dengeli bir risk/getiri elde edebileceğinizi hesaplar.
        </p>
        <p style="color:var(--ink-dim); font-size:13px; margin-top:-8px;">
            Bu bir yatırım tavsiyesi değildir — geçmiş fiyat verisine dayalı, istatistiksel bir araçtır.
            "Mevcut" ağırlık burada eşit dağılım (1/N) varsayımıyla hesaplanır — favorilerinizde gerçek bir pay bilgisi tutulmaz.
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:20px; align-items:flex-end; margin-bottom:14px;">
            <div>
                <label style="color:var(--ink-dim); font-size:13px; display:block; margin-bottom:6px;">Min. Ağırlık (%)</label>
                <input type="number" id="opt-min-agirlik" value="0" min="0" max="100" step="1"
                       style="width:90px; background:var(--panel); border:1px solid var(--line); color:var(--ink); border-radius:6px; padding:7px 9px; font-size:14px;">
            </div>
            <div>
                <label style="color:var(--ink-dim); font-size:13px; display:block; margin-bottom:6px;">Max. Ağırlık (%)</label>
                <input type="number" id="opt-max-agirlik" value="50" min="0" max="100" step="1"
                       style="width:90px; background:var(--panel); border:1px solid var(--line); color:var(--ink); border-radius:6px; padding:7px 9px; font-size:14px;">
            </div>
            <button onclick="optimizasyonCalistir()" style="background:var(--blue); color:white; border:none; border-radius:8px; padding:9px 18px; font-weight:600; cursor:pointer; font-size:14px;">Optimize Et</button>
        </div>
        <div id="opt-durum" style="color:var(--ink-dim); font-size:13px;"></div>
        <div id="opt-sonuc" style="display:none; margin-top:12px;">
            <div style="display:flex; gap:28px; margin-bottom:12px;">
                <div>
                    <div style="color:var(--ink-dim); font-size:12px;">Eşit Ağırlıkta Sharpe (yıllık)</div>
                    <div id="opt-mevcut-sharpe" style="font-size:20px; font-weight:700;">—</div>
                </div>
                <div>
                    <div style="color:var(--ink-dim); font-size:12px;">Önerilen Sharpe (yıllık)</div>
                    <div id="opt-onerilen-sharpe" style="font-size:20px; font-weight:700; color:var(--green);">—</div>
                </div>
            </div>
            <div class="mini-table-wrap" style="overflow-x:auto;">
                <table class="mini" id="opt-table" style="font-size:13px;"></table>
            </div>
        </div>
    </div>
</div>

<p style="color:var(--ink-dim); font-size:13px;">
    Bu liste sadece bu cihazda/tarayıcıda saklanır — başka bir cihazda görünmez.
</p>

<style>
.fav-table th {{ cursor: pointer; user-select: none; white-space: nowrap; }}
.fav-table th:hover {{ color: var(--teal-bright); }}
.fav-table th .sort-arrow {{ opacity: 0.5; font-size: 10px; margin-left: 3px; }}
.fav-table td.fon-adi {{ min-width: 190px; max-width: 190px; }}
.fav-table th.fon-adi {{ min-width: 190px; }}
.fav-table .fon-adi-inner {{
    font-size: 11px; line-height: 1.3;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
    overflow: hidden;
}}
</style>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const FAV_KEY = 'fonlarca_favoriler';
const RISK_FREE_RATE_YILLIK = {RISK_FREE_RATE};  // TLREF, script'te elle güncellenir
function getFavorites() {{
    try {{ return JSON.parse(localStorage.getItem(FAV_KEY)) || []; }}
    catch(e) {{ return []; }}
}}
function removeFavorite(kod) {{
    const favs = getFavorites().filter(f => f !== kod);
    try {{ localStorage.setItem(FAV_KEY, JSON.stringify(favs)); }} catch(e) {{}}
    loadAll();
}}

function fmtPct(v) {{
    if (v == null) return '—';
    return (v >= 0 ? '+' : '') + v.toLocaleString('tr-TR', {{minimumFractionDigits:2, maximumFractionDigits:2}}) + '%';
}}
function fmtTL(v) {{
    if (v == null) return '—';
    const abs = Math.abs(v);
    let s;
    if (abs >= 1e9) s = (v/1e9).toLocaleString('tr-TR', {{minimumFractionDigits:1, maximumFractionDigits:1}}) + ' Mlr';
    else if (abs >= 1e6) s = (v/1e6).toLocaleString('tr-TR', {{minimumFractionDigits:1, maximumFractionDigits:1}}) + ' Mn';
    else s = v.toLocaleString('tr-TR', {{minimumFractionDigits:1, maximumFractionDigits:1}});
    return (v >= 0 ? '+' : '') + s + ' TL';
}}
function fmtTLLabel(v) {{
    if (v == null) return '—';
    const abs = Math.abs(v);
    let s;
    if (abs >= 1e9) s = (v/1e9).toLocaleString('tr-TR', {{minimumFractionDigits:1, maximumFractionDigits:1}}) + ' Mlr';
    else if (abs >= 1e6) s = (v/1e6).toLocaleString('tr-TR', {{minimumFractionDigits:1, maximumFractionDigits:1}}) + ' Mn';
    else s = v.toLocaleString('tr-TR', {{minimumFractionDigits:1, maximumFractionDigits:1}});
    return (v >= 0 ? '+' : '') + s;
}}
function fmtInt(v) {{
    if (v == null) return '—';
    return (v >= 0 ? '+' : '') + Math.round(v).toLocaleString('tr-TR');
}}

/* --- dönem hesaplamaları: günlük seri (son ~35 gün) + aylık seri --- */
function sumLastNDaily(arr, n) {{
    if (!arr || !arr.length) return null;
    const slice = arr.slice(-n).filter(v => v != null);
    if (!slice.length) return null;
    return slice.reduce((a,b) => a+b, 0);
}}
function sumMonthly(arr, aylar, n, ytd) {{
    if (!arr || !arr.length) return null;
    let idxs;
    if (ytd) {{
        const year = (aylar[aylar.length-1] || '').slice(0,4);
        idxs = aylar.map((a,i) => a.startsWith(year) ? i : -1).filter(i => i >= 0);
    }} else {{
        idxs = [];
        for (let i = Math.max(0, arr.length - n); i < arr.length; i++) idxs.push(i);
    }}
    const vals = idxs.map(i => arr[i]).filter(v => v != null);
    if (!vals.length) return null;
    return vals.reduce((a,b) => a+b, 0);
}}
function diffLastNDaily(arr, n) {{
    if (!arr) return null;
    const slice = arr.slice(-n).filter(v => v != null);
    if (slice.length < 2) return null;
    return slice[slice.length-1] - slice[0];
}}
function diffMonthly(arr, aylar, n, ytd) {{
    if (!arr || !arr.length) return null;
    let idxs;
    if (ytd) {{
        const year = (aylar[aylar.length-1] || '').slice(0,4);
        idxs = aylar.map((a,i) => a.startsWith(year) ? i : -1).filter(i => i >= 0);
        if (idxs.length) idxs = [Math.max(0, idxs[0]-1), ...idxs]; // yılbaşı öncesi bir nokta daha (başlangıç referansı)
    }} else {{
        idxs = [];
        for (let i = Math.max(0, arr.length - n - 1); i < arr.length; i++) idxs.push(i);
    }}
    const vals = idxs.map(i => arr[i]).filter(v => v != null);
    if (vals.length < 2) return null;
    return vals[vals.length-1] - vals[0];
}}

function cashflowFor(d, period) {{
    const g = (d.akislar && d.akislar.gunluk) || {{}};
    const m = d.akislar || {{}};
    if (period === 'Günlük') {{ const arr = g.net_nakit_akisi || []; return arr.length ? arr[arr.length-1] : null; }}
    if (period === 'Haftalık') return sumLastNDaily(g.net_nakit_akisi, 7);
    if (period === 'Aylık') return sumLastNDaily(g.net_nakit_akisi, 30);
    if (period === '3 Aylık') return sumMonthly(m.net_nakit_akisi, m.aylar, 3, false);
    if (period === '6 Aylık') return sumMonthly(m.net_nakit_akisi, m.aylar, 6, false);
    if (period === 'YBB') return sumMonthly(m.net_nakit_akisi, m.aylar, null, true);
    if (period === 'Yıllık') return sumMonthly(m.net_nakit_akisi, m.aylar, 12, false);
    return null;
}}
function investorChangeFor(d, period) {{
    const g = (d.akislar && d.akislar.gunluk) || {{}};
    const m = d.akislar || {{}};
    if (period === 'Günlük') return diffLastNDaily(g.yatirimci_sayisi, 2);
    if (period === 'Haftalık') return diffLastNDaily(g.yatirimci_sayisi, 7);
    if (period === 'Aylık') return diffLastNDaily(g.yatirimci_sayisi, 30);
    if (period === '3 Aylık') return diffMonthly(m.yatirimci_sayisi, m.aylar, 3, false);
    if (period === '6 Aylık') return diffMonthly(m.yatirimci_sayisi, m.aylar, 6, false);
    if (period === 'YBB') return diffMonthly(m.yatirimci_sayisi, m.aylar, null, true);
    if (period === 'Yıllık') return diffMonthly(m.yatirimci_sayisi, m.aylar, 12, false);
    return null;
}}

let fundsData = {{}};
let currentPeriod = 'Günlük';
let cashflowChart, investorChart;

const RETURN_COLS = [
    ['Günlük','Günlük'], ['Haftalık','Haftalık'], ['Aylık','Aylık'], ['3 Ay','3 Aylık'],
    ['6 Ay','6 Aylık'], ['Yılbaşı','YBB'], ['1 Yıl','Yıllık'],
];
let sortKey = null, sortDir = 1;

function truncate(s, n) {{
    if (!s) return '—';
    return s.length > n ? s.slice(0, n) + '…' : s;
}}

function sortedFavs(favs) {{
    if (!sortKey) return favs;
    const withData = favs.map(kod => ({{ kod, v: sortKey === 'kod' ? kod :
        (sortKey === 'ad' ? (fundsData[kod] && fundsData[kod].fon_adi) || '' :
        (fundsData[kod] && fundsData[kod].getiriler ? fundsData[kod].getiriler[sortKey] : null)) }}));
    withData.sort((a, b) => {{
        if (a.v == null && b.v == null) return 0;
        if (a.v == null) return 1;
        if (b.v == null) return -1;
        if (typeof a.v === 'string') return sortDir * a.v.localeCompare(b.v, 'tr');
        return sortDir * (a.v - b.v);
    }});
    return withData.map(x => x.kod);
}}

function renderTable(favsRaw) {{
    const favs = sortedFavs(favsRaw);
    const arrow = (key) => sortKey === key ? '<span class="sort-arrow">' + (sortDir === 1 ? '▲' : '▼') + '</span>' : '';
    let thead = '<tr>' +
        '<th onclick="setSort(\\'kod\\')">Kod' + arrow('kod') + '</th>' +
        '<th class="fon-adi" onclick="setSort(\\'ad\\')">Fon Adı' + arrow('ad') + '</th>' +
        RETURN_COLS.map(c => '<th onclick="setSort(\\'' + c[0] + '\\')">' + c[1] + arrow(c[0]) + '</th>').join('') +
        '<th></th></tr>';
    let rows = favs.map(kod => {{
        const d = fundsData[kod];
        if (!d) return '<tr><td>' + kod + '</td><td colspan="' + (RETURN_COLS.length+2) + '" style="color:var(--ink-dim);">Veri yüklenemedi</td></tr>';
        const getiriler = d.getiriler || {{}};
        const tds = RETURN_COLS.map(c => {{
            const v = getiriler[c[0]];
            if (v == null) return '<td>—</td>';
            const cls = v >= 0 ? 'good' : 'bad';
            return '<td><span class="score-badge ' + cls + '">' + fmtPct(v) + '</span></td>';
        }}).join('');
        return '<tr>' +
            '<td><a href="fon-karti.html?kod=' + kod + '">' + kod + '</a></td>' +
            '<td class="fon-adi"><div class="fon-adi-inner">' + truncate(d.fon_adi, 40) + '</div></td>' + tds +
            '<td><button onclick="removeFavorite(\\'' + kod + '\\')" style="background:transparent;border:1px solid var(--line);color:var(--red);border-radius:6px;padding:3px 10px;cursor:pointer;">Kaldır</button></td>' +
            '</tr>';
    }}).join('');
    document.getElementById('fav-returns-table').innerHTML = thead + rows;
}}
function setSort(key) {{
    if (sortKey === key) sortDir *= -1; else {{ sortKey = key; sortDir = 1; }}
    renderTable(getFavorites());
}}

function valueLabelPlugin(fmt) {{
    return {{
        id: 'valueLabel' + Math.random().toString(36).slice(2),
        afterDatasetsDraw(chart) {{
            const {{ ctx }} = chart;
            chart.data.datasets.forEach((ds, dsIndex) => {{
                const meta = chart.getDatasetMeta(dsIndex);
                meta.data.forEach((bar, i) => {{
                    const v = ds.data[i];
                    if (v == null) return;
                    ctx.save();
                    ctx.fillStyle = '#c9cdd6';
                    ctx.font = '600 10px -apple-system,Segoe UI,Arial,sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = v >= 0 ? 'bottom' : 'top';
                    ctx.fillText(fmt(v), bar.x, bar.y + (v >= 0 ? -4 : 4));
                    ctx.restore();
                }});
            }});
        }}
    }};
}}
function makeChart(canvasId, tooltipFmt, labelFmt) {{
    return new Chart(document.getElementById(canvasId), {{
        type: 'bar',
        data: {{ labels: [], datasets: [{{ data: [], backgroundColor: [] }}] }},
        options: {{
            maintainAspectRatio: false,
            layout: {{ padding: {{ top: 16, bottom: 16 }} }},
            plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => tooltipFmt(c.raw) }} }} }},
            scales: {{ x: {{ ticks: {{ color: '#9aa0ac', font: {{ size: 11 }} }}, grid: {{ display: false }} }},
                       y: {{ display: false, grid: {{ display: false }} }} }}
        }},
        plugins: [valueLabelPlugin(labelFmt)]
    }});
}}

function updateCharts(favs) {{
    const cfVals = favs.map(kod => fundsData[kod] ? cashflowFor(fundsData[kod], currentPeriod) : null);
    const ivVals = favs.map(kod => fundsData[kod] ? investorChangeFor(fundsData[kod], currentPeriod) : null);
    const posColor = 'rgba(76,187,109,0.75)', negColor = 'rgba(224,90,90,0.75)';

    cashflowChart.data.labels = favs;
    cashflowChart.data.datasets[0].data = cfVals;
    cashflowChart.data.datasets[0].backgroundColor = cfVals.map(v => v == null ? '#3a3d48' : (v >= 0 ? posColor : negColor));
    cashflowChart.update();

    investorChart.data.labels = favs;
    investorChart.data.datasets[0].data = ivVals;
    investorChart.data.datasets[0].backgroundColor = ivVals.map(v => v == null ? '#3a3d48' : (v >= 0 ? posColor : negColor));
    investorChart.update();
}}

function loadAll() {{
    const favs = getFavorites();
    if (!favs.length) {{
        document.getElementById('fav-empty').style.display = 'block';
        document.getElementById('fav-body').style.display = 'none';
        document.getElementById('fav-charts').style.display = 'none';
        return;
    }}
    document.getElementById('fav-empty').style.display = 'none';
    document.getElementById('fav-body').style.display = 'block';
    document.getElementById('fav-charts').style.display = 'block';

    Promise.all(favs.map(kod =>
        fetch('data/fon-kartlari/' + kod + '.json').then(r => r.ok ? r.json() : null).catch(() => null)
    )).then(results => {{
        fundsData = {{}};
        favs.forEach((kod, i) => {{ fundsData[kod] = results[i]; }});
        renderTable(favs);
        if (!cashflowChart) {{
            cashflowChart = makeChart('fav-cashflow-chart', fmtTL, fmtTLLabel);
            investorChart = makeChart('fav-investor-chart', fmtInt, fmtInt);
        }}
        updateCharts(favs);
    }});
}}

{SHARPE_OPT_JS}

function optimizasyonCalistir() {{
    const kodlar = getFavorites();
    const n = kodlar.length;
    const esitAgirliklar = {{}};
    kodlar.forEach(k => {{ esitAgirliklar[k] = n > 0 ? 1 / n : 0; }});

    sharpeOptimizasyonuCalistir(kodlar, esitAgirliklar, 'opt-min-agirlik', 'opt-max-agirlik', {{
        durum: 'opt-durum', sonuc: 'opt-sonuc',
        mevcutSharpe: 'opt-mevcut-sharpe', onerilenSharpe: 'opt-onerilen-sharpe', tablo: 'opt-table',
        mevcutEtiket: 'Eşit Ağırlık',
    }});
}}

document.getElementById('fav-period-tabs').querySelectorAll('.period-tab').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('#fav-period-tabs .period-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPeriod = btn.dataset.p;
        updateCharts(getFavorites());
    }});
}});

loadAll();
</script>"""

    with open("docs/favoriler.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA — Favorilerim", "favoriler.html", body))
    print("Favorilerim sayfası oluşturuldu: docs/favoriler.html")


# ------------------------------------------------------------------
# Sayfa 6: Portföyüm (cihaz-lokali, localStorage — sunucu tarafında veri yok)
# ------------------------------------------------------------------

def write_portfoyum_page(anchor):
    body = f"""{page_header('portfoyum.html', 'Portföyüm', anchor)}

<div class="card">
    <h2 style="color:var(--teal-bright); margin-top:0;">💼 Portföyüm</h2>
    <div class="fund-search-wrap" style="max-width:420px; margin-left:0;">
        <input type="text" id="pf-add-input" list="pf-add-list" placeholder="🔍 Fon ekle (kod veya isim)…" autocomplete="off">
        <datalist id="pf-add-list"></datalist>
    </div>
    <div id="pf-empty" style="display:none; color:var(--ink-dim); padding:16px 0;">
        Portföyünüz boş. Yukarıdan bir fon arayıp ekleyebilirsiniz.
    </div>
    <div id="pf-body" style="display:none;">
        <div class="mini-table-wrap" style="overflow-x:auto; margin-top:14px;">
            <table class="mini pf-table" id="pf-table" style="font-size:13px;"></table>
        </div>
    </div>
</div>

<div id="pf-summary-wrap" style="display:none;">
    <div class="card">
        <div class="period-tabs" id="pf-currency-tabs">
            <button class="period-tab active" data-c="TL">TL</button>
            <button class="period-tab" data-c="USD">USD</button>
            <button class="period-tab" data-c="EUR">EUR</button>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:28px; align-items:center;">
            <div>
                <div style="color:var(--ink-dim); font-size:13px;">Portföyün Güncel Değeri</div>
                <div id="pf-total-value" style="font-size:26px; font-weight:700;">—</div>
            </div>
            <div>
                <div style="color:var(--ink-dim); font-size:13px;">Bir Önceki Güne Göre Değişim</div>
                <div id="pf-daily-change" style="font-size:20px; font-weight:700;">—</div>
            </div>
            <div>
                <div style="color:var(--ink-dim); font-size:13px;">Bir Önceki Güne Göre Değişim (%)</div>
                <div id="pf-daily-change-pct" style="font-size:20px; font-weight:700;">—</div>
            </div>
            <div id="pf-mood" style="font-size:40px;">—</div>
        </div>
    </div>

    <div class="card">
        <h3 style="color:var(--ink); margin-top:0;">Fon Bazında Günlük Kazanç/Kayıp</h3>
        <div style="height:300px;"><canvas id="pf-daily-pnl-chart"></canvas></div>
    </div>

    <div class="kat-cols">
        <div class="card">
            <h3 style="color:var(--ink); margin-top:0;">Portföyün Son Tarihli Varlık Dağılımı</h3>
            <div style="height:400px;"><canvas id="pf-alloc-chart"></canvas></div>
        </div>
        <div class="card">
            <h3 style="color:var(--ink); margin-top:0;">Portföyün Son Tarihli Risk Derecesi</h3>
            <div id="pf-risk-gauge" style="text-align:center; padding-top:10px;"></div>
        </div>
    </div>

    <div class="card">
        <h3 style="color:var(--ink); margin-top:0; font-size:20px;">🎯 Fon Dağılım Optimizasyonu</h3>
        <p style="color:var(--ink-dim); font-size:14px; margin-top:-2px;">
            Elinizdeki fonları hangi oranlarda tutarsanız, geçmiş verilere göre daha dengeli bir risk/getiri elde edebileceğinizi hesaplar.
        </p>
        <p style="color:var(--ink-dim); font-size:13px; margin-top:-8px;">
            Bu bir yatırım tavsiyesi değildir — geçmiş fiyat verisine dayalı, istatistiksel bir araçtır.
            Geçmiş performans ve fonlar arası ilişkiler gelecekte aynı kalmayabilir.
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:20px; align-items:flex-end; margin-bottom:14px;">
            <div>
                <label style="color:var(--ink-dim); font-size:13px; display:block; margin-bottom:6px;">Min. Ağırlık (%)</label>
                <input type="number" id="opt-min-agirlik" value="0" min="0" max="100" step="1"
                       style="width:90px; background:var(--panel); border:1px solid var(--line); color:var(--ink); border-radius:6px; padding:7px 9px; font-size:14px;">
            </div>
            <div>
                <label style="color:var(--ink-dim); font-size:13px; display:block; margin-bottom:6px;">Max. Ağırlık (%)</label>
                <input type="number" id="opt-max-agirlik" value="50" min="0" max="100" step="1"
                       style="width:90px; background:var(--panel); border:1px solid var(--line); color:var(--ink); border-radius:6px; padding:7px 9px; font-size:14px;">
            </div>
            <button onclick="optimizasyonCalistir()" style="background:var(--blue); color:white; border:none; border-radius:8px; padding:9px 18px; font-weight:600; cursor:pointer; font-size:14px;">Optimize Et</button>
        </div>
        <div id="opt-durum" style="color:var(--ink-dim); font-size:13px;"></div>
        <div id="opt-sonuc" style="display:none; margin-top:12px;">
            <div style="display:flex; gap:28px; margin-bottom:12px;">
                <div>
                    <div style="color:var(--ink-dim); font-size:12px;">Mevcut Sharpe (yıllık)</div>
                    <div id="opt-mevcut-sharpe" style="font-size:20px; font-weight:700;">—</div>
                </div>
                <div>
                    <div style="color:var(--ink-dim); font-size:12px;">Önerilen Sharpe (yıllık)</div>
                    <div id="opt-onerilen-sharpe" style="font-size:20px; font-weight:700; color:var(--green);">—</div>
                </div>
            </div>
            <div class="mini-table-wrap" style="overflow-x:auto;">
                <table class="mini" id="opt-table" style="font-size:13px;"></table>
            </div>
        </div>
    </div>
</div>

<p style="color:var(--ink-dim); font-size:13px;">
    Bu portföy sadece bu cihazda/tarayıcıda saklanır — başka bir cihazda görünmez.
    Fon Fiyatı, Risk Değeri ve Varlık Dağılımı bilgileri günlük olarak güncellenir; siz sadece Fon Pay Adedi'ni giriyorsunuz.
</p>

<style>
.pf-table td.fon-adi {{ min-width: 170px; max-width: 170px; }}
.pf-table .fon-adi-inner {{
    font-size: 11px; line-height: 1.3;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden;
}}
.pf-pay-input {{
    width: 90px; background: var(--panel); border: 1px solid var(--line); color: var(--ink);
    border-radius: 6px; padding: 4px 6px; font-size: 13px;
}}
</style>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const PORTFOY_KEY = 'fonlarca_portfoy';
const RISK_FREE_RATE_YILLIK = {RISK_FREE_RATE};  // TLREF, script'te elle güncellenir
function getPortfoy() {{
    try {{ return JSON.parse(localStorage.getItem(PORTFOY_KEY)) || {{}}; }}
    catch(e) {{ return {{}}; }}
}}
function setPortfoy(p) {{
    try {{ localStorage.setItem(PORTFOY_KEY, JSON.stringify(p)); }} catch(e) {{}}
}}
function removeFund(kod) {{
    const p = getPortfoy();
    delete p[kod];
    setPortfoy(p);
    render();
}}
function setPay(kod, val) {{
    const p = getPortfoy();
    const n = parseFloat(val.replace(',', '.'));
    p[kod] = isNaN(n) ? 0 : n;
    setPortfoy(p);
    recalcAndRender();
}}

let fundsData = {{}};
let benchmarks = {{}};
let currency = 'TL';

function fmtNum(v, decimals) {{
    if (v == null || isNaN(v)) return '—';
    return v.toLocaleString('tr-TR', {{minimumFractionDigits: decimals, maximumFractionDigits: decimals}});
}}
function fmtMoney(v) {{
    if (v == null || isNaN(v)) return '—';
    const sym = currency === 'TL' ? ' TL' : (currency === 'USD' ? ' $' : ' €');
    return fmtNum(v, 0) + sym;
}}

// Seçili para birimi bugün için 1 birim = kaç TL (TL seçiliyse 1)
function fxRateFor(dateStr) {{
    if (currency === 'TL') return 1;
    const series = benchmarks[currency];
    if (!series || !series.length) return null;
    // dateStr'a en yakın (o veya önceki) noktayı bul
    let rate = null;
    for (const p of series) {{
        if (p.time <= dateStr) rate = p.value; else break;
    }}
    return rate || (series.length ? series[series.length - 1].value : null);
}}

function truncate(s, n) {{
    if (!s) return '—';
    return s.length > n ? s.slice(0, n) + '…' : s;
}}
function gunlukDegisimHucre(v) {{
    if (v == null) return '—';
    const cls = v >= 0 ? 'good' : 'bad';
    const txt = (v >= 0 ? '+' : '') + v.toLocaleString('tr-TR', {{minimumFractionDigits:2, maximumFractionDigits:2}}) + '%';
    return '<span class="score-badge ' + cls + '">' + txt + '</span>';
}}

function renderTable(portfoy) {{
    const kodlar = Object.keys(portfoy);
    let toplamTL = 0;
    kodlar.forEach(k => {{
        const d = fundsData[k];
        if (!d) return;
        const fiyat = d._sonFiyat;
        if (fiyat != null) toplamTL += fiyat * (portfoy[k] || 0);
    }});

    let thead = '<tr><th>Kod</th><th>Fon Adı</th><th>Fon Fiyatı</th><th>Günlük Değişim (%)</th><th>Risk Değeri</th>' +
        '<th>Fon Pay Adedi</th><th>Toplam Değer (TL)</th><th>Portföy İçindeki Ağırlığı (%)</th><th></th></tr>';
    let rows = kodlar.map(kod => {{
        const d = fundsData[kod];
        if (!d) return '<tr><td>' + kod + '</td><td colspan="7" style="color:var(--ink-dim);">Veri yüklenemedi</td></tr>';
        const pay = portfoy[kod] || 0;
        const fiyat = d._sonFiyat;
        const deger = fiyat != null ? fiyat * pay : null;
        const agirlik = (deger != null && toplamTL > 0) ? (deger / toplamTL * 100) : null;
        return '<tr>' +
            '<td><a href="fon-karti.html?kod=' + kod + '">' + kod + '</a></td>' +
            '<td class="fon-adi"><div class="fon-adi-inner">' + truncate(d.fon_adi, 40) + '</div></td>' +
            '<td>' + (fiyat != null ? fiyat.toLocaleString('tr-TR', {{minimumFractionDigits:4, maximumFractionDigits:4}}) : '—') + '</td>' +
            '<td>' + gunlukDegisimHucre(d.getiriler && d.getiriler['Günlük']) + '</td>' +
            '<td>' + (d.risk_degeri != null ? Math.round(d.risk_degeri) + '/7' : '—') + '</td>' +
            '<td><input class="pf-pay-input" type="text" value="' + (pay || '') + '" placeholder="0" onchange="setPay(\\'' + kod + '\\', this.value)"></td>' +
            '<td>' + (deger != null ? fmtNum(deger, 2) : '—') + '</td>' +
            '<td>' + (agirlik != null ? fmtNum(agirlik, 2) + '%' : '—') + '</td>' +
            '<td><button onclick="removeFund(\\'' + kod + '\\')" style="background:transparent;border:1px solid var(--line);color:var(--red);border-radius:6px;padding:3px 10px;cursor:pointer;">Kaldır</button></td>' +
            '</tr>';
    }}).join('');
    document.getElementById('pf-table').innerHTML = thead + rows;
}}

function weightedAllocation(portfoy) {{
    const kodlar = Object.keys(portfoy);
    let toplamTL = 0;
    const agirliklar = {{}};
    kodlar.forEach(k => {{
        const d = fundsData[k];
        if (!d || d._sonFiyat == null) return;
        const deger = d._sonFiyat * (portfoy[k] || 0);
        agirliklar[k] = deger;
        toplamTL += deger;
    }});
    if (toplamTL <= 0) return {{}};
    const sonuc = {{}};
    kodlar.forEach(k => {{
        const d = fundsData[k];
        const w = (agirliklar[k] || 0) / toplamTL;
        const dagilim = (d && d.varlik_dagilimi && d.varlik_dagilimi.son_tarihli) || {{}};
        Object.keys(dagilim).forEach(kat => {{
            sonuc[kat] = (sonuc[kat] || 0) + dagilim[kat] * w;
        }});
    }});
    return sonuc;
}}

function weightedRisk(portfoy) {{
    const kodlar = Object.keys(portfoy);
    let toplamTL = 0, toplamRiskAgirlikli = 0;
    kodlar.forEach(k => {{
        const d = fundsData[k];
        if (!d || d._sonFiyat == null || d.risk_degeri == null) return;
        const deger = d._sonFiyat * (portfoy[k] || 0);
        toplamTL += deger;
        toplamRiskAgirlikli += deger * d.risk_degeri;
    }});
    if (toplamTL <= 0) return null;
    return toplamRiskAgirlikli / toplamTL;
}}

{SHARPE_OPT_JS}

function optimizasyonCalistir() {{
    const portfoy = getPortfoy();
    const kodlar = Object.keys(portfoy);
    const toplamTL = {{}};
    let genelToplam = 0;
    kodlar.forEach(k => {{
        const d = fundsData[k];
        if (!d || d._sonFiyat == null) return;
        const deger = d._sonFiyat * (portfoy[k] || 0);
        toplamTL[k] = deger;
        genelToplam += deger;
    }});
    const mevcutAgirliklar = {{}};
    kodlar.forEach(k => {{ mevcutAgirliklar[k] = genelToplam > 0 ? (toplamTL[k] || 0) / genelToplam : 0; }});

    sharpeOptimizasyonuCalistir(kodlar, mevcutAgirliklar, 'opt-min-agirlik', 'opt-max-agirlik', {{
        durum: 'opt-durum', sonuc: 'opt-sonuc',
        mevcutSharpe: 'opt-mevcut-sharpe', onerilenSharpe: 'opt-onerilen-sharpe', tablo: 'opt-table',
    }});
}}

function fonBazindaGunlukPnl(portfoy) {{
    const kodlar = Object.keys(portfoy);
    const sonuc = [];
    kodlar.forEach(k => {{
        const d = fundsData[k];
        if (!d || d._sonFiyat == null || d._oncekiFiyat == null) return;
        const pay = portfoy[k] || 0;
        const pnlTL = (d._sonFiyat - d._oncekiFiyat) * pay;
        sonuc.push({{ kod: k, pnlTL }});
    }});
    // Z-A: en yüksek kazançtan en düşük/en çok kayba doğru
    sonuc.sort((a, b) => b.pnlTL - a.pnlTL);
    return sonuc;
}}

let dailyPnlChart = null;

function renderDailyPnlChart(portfoy) {{
    const veriler = fonBazindaGunlukPnl(portfoy);
    const bugunTarihi = Object.values(fundsData).find(d => d && d._sonTarih)?._sonTarih;
    const fx = fxRateFor(bugunTarihi || '9999-99-99');
    const labels = veriler.map(v => v.kod);
    const data = veriler.map(v => (fx && currency !== 'TL') ? v.pnlTL / fx : v.pnlTL);
    const posColor = 'rgba(76,187,109,0.75)', negColor = 'rgba(224,90,90,0.75)';
    if (dailyPnlChart) {{ dailyPnlChart.destroy(); }}
    dailyPnlChart = new Chart(document.getElementById('pf-daily-pnl-chart'), {{
        type: 'bar',
        data: {{ labels, datasets: [{{ data, backgroundColor: data.map(v => v >= 0 ? posColor : negColor) }}] }},
        options: {{
            maintainAspectRatio: false,
            layout: {{ padding: {{ top: 16, bottom: 16 }} }},
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{ callbacks: {{ label: c => fmtMoney(c.raw) }} }}
            }},
            scales: {{
                x: {{ ticks: {{ color: '#9aa0ac', font: {{ size: 11 }} }}, grid: {{ display: false }} }},
                y: {{ display: false, grid: {{ display: false }} }}
            }}
        }},
        plugins: [{{
            id: 'pfDailyPnlLabels',
            afterDatasetsDraw(chart) {{
                const {{ ctx }} = chart;
                const meta = chart.getDatasetMeta(0);
                meta.data.forEach((bar, i) => {{
                    ctx.save();
                    ctx.fillStyle = '#c9cdd6';
                    ctx.font = '600 10px -apple-system,Segoe UI,Arial,sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = data[i] >= 0 ? 'bottom' : 'top';
                    ctx.fillText(fmtMoney(data[i]), bar.x, bar.y + (data[i] >= 0 ? -4 : 4));
                    ctx.restore();
                }});
            }}
        }}]
    }});
}}

let allocChart = null;

function renderAllocChart(dagilim) {{
    const entries = Object.entries(dagilim).sort((a, b) => b[1] - a[1]).filter(e => e[1] > 0);
    const labels = entries.map(e => e[0]);
    const data = entries.map(e => Math.round(e[1] * 100) / 100);
    const colors = ['#4a90d9','#e0b23f','#4cbb6d','#a06fd0','#e07a5f','#4cbbb0','#d94a6f','#8ea04a','#d97a4a','#6f8ed0'];
    if (allocChart) {{ allocChart.destroy(); }}
    allocChart = new Chart(document.getElementById('pf-alloc-chart'), {{
        type: 'bar',
        data: {{ labels, datasets: [{{ data, backgroundColor: labels.map((_, i) => colors[i % colors.length]) }}] }},
        options: {{
            indexAxis: 'y',
            maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => '%' + fmtNum(c.raw, 2) }} }} }},
            scales: {{
                x: {{ display: false, grid: {{ display: false }} }},
                y: {{ ticks: {{ color: '#c9cdd6', font: {{ size: 11 }} }}, grid: {{ display: false }} }}
            }}
        }},
        plugins: [{{
            id: 'pfAllocLabels',
            afterDatasetsDraw(chart) {{
                const {{ ctx }} = chart;
                const meta = chart.getDatasetMeta(0);
                meta.data.forEach((bar, i) => {{
                    ctx.save();
                    ctx.fillStyle = '#c9cdd6';
                    ctx.font = '600 11px -apple-system,Segoe UI,Arial,sans-serif';
                    ctx.textAlign = 'left';
                    ctx.textBaseline = 'middle';
                    ctx.fillText('%' + fmtNum(data[i], 2), bar.x + 6, bar.y);
                    ctx.restore();
                }});
            }}
        }}]
    }});
}}

function renderRiskGauge(risk) {{
    const box = document.getElementById('pf-risk-gauge');
    if (risk == null) {{ box.innerHTML = '<p style="color:var(--ink-dim);">Veri yok</p>'; return; }}
    const rounded = Math.round(risk);
    const label = rounded <= 2 ? 'Düşük Riskli' : (rounded <= 5 ? 'Orta Riskli' : 'Yüksek Riskli');
    const color = rounded <= 2 ? 'var(--green)' : (rounded <= 5 ? '#e0b23f' : 'var(--red)');
    // Yarım daire gösterge: 1..7 değeri -180..0 derece arasına eşlenir
    const angle = -180 + ((rounded - 1) / 6) * 180;
    const rad = angle * Math.PI / 180;
    const cx = 110, cy = 100, r = 80;
    const nx = cx + r * 0.85 * Math.cos(rad), ny = cy + r * 0.85 * Math.sin(rad);
    box.innerHTML = `
        <svg viewBox="0 0 220 130" style="max-width:260px;">
            <path d="M 30 100 A 80 80 0 0 1 71 27" stroke="#4cbb6d" stroke-width="16" fill="none" />
            <path d="M 71 27 A 80 80 0 0 1 149 27" stroke="#e0b23f" stroke-width="16" fill="none" />
            <path d="M 149 27 A 80 80 0 0 1 190 100" stroke="#e05a5a" stroke-width="16" fill="none" />
            <line x1="${{cx}}" y1="${{cy}}" x2="${{nx}}" y2="${{ny}}" stroke="#c9cdd6" stroke-width="4" />
            <circle cx="${{cx}}" cy="${{cy}}" r="7" fill="#c9cdd6" />
        </svg>
        <div style="font-size:34px; font-weight:700; color:var(--ink); margin-top:-6px;">${{rounded}}/7</div>
        <div style="font-size:22px; font-weight:600; color:${{color}};">${{label}}</div>
    `;
}}

function recalcAndRender() {{
    const portfoy = getPortfoy();
    const kodlar = Object.keys(portfoy);
    if (!kodlar.length) {{
        document.getElementById('pf-empty').style.display = 'block';
        document.getElementById('pf-body').style.display = 'none';
        document.getElementById('pf-summary-wrap').style.display = 'none';
        return;
    }}
    document.getElementById('pf-empty').style.display = 'none';
    document.getElementById('pf-body').style.display = 'block';
    document.getElementById('pf-summary-wrap').style.display = 'block';

    renderTable(portfoy);

    // Bugünkü ve dünkü toplam TL değeri (pay sabit varsayımıyla)
    let toplamBugunTL = 0, toplamDunTL = 0;
    kodlar.forEach(k => {{
        const d = fundsData[k];
        if (!d) return;
        const pay = portfoy[k] || 0;
        if (d._sonFiyat != null) toplamBugunTL += d._sonFiyat * pay;
        if (d._oncekiFiyat != null) toplamDunTL += d._oncekiFiyat * pay;
    }});

    const bugunTarihi = Object.values(fundsData)[0] ? Object.values(fundsData).find(d => d && d._sonTarih)?._sonTarih : null;
    const fx = fxRateFor(bugunTarihi || '9999-99-99');
    const gosterilenToplam = (fx && currency !== 'TL') ? toplamBugunTL / fx : toplamBugunTL;
    document.getElementById('pf-total-value').textContent = fmtMoney(gosterilenToplam);

    if (toplamDunTL > 0) {{
        const degisimTL = toplamBugunTL - toplamDunTL;
        const degisimPct = (degisimTL / toplamDunTL) * 100;
        const gosterilenDegisim = (fx && currency !== 'TL') ? degisimTL / fx : degisimTL;
        document.getElementById('pf-daily-change').textContent = (degisimTL >= 0 ? '+' : '') + fmtMoney(gosterilenDegisim);
        document.getElementById('pf-daily-change').style.color = degisimTL >= 0 ? 'var(--green)' : 'var(--red)';
        document.getElementById('pf-daily-change-pct').textContent = (degisimPct >= 0 ? '+' : '') + fmtNum(degisimPct, 2) + '%';
        document.getElementById('pf-daily-change-pct').style.color = degisimPct >= 0 ? 'var(--green)' : 'var(--red)';

        let mood = '😞';
        if (degisimPct >= 0.5) mood = '🏆';
        else if (degisimPct >= 0.25) mood = '🎉';
        else if (degisimPct >= 0) mood = '😊';
        document.getElementById('pf-mood').textContent = mood;
    }} else {{
        document.getElementById('pf-daily-change').textContent = '—';
        document.getElementById('pf-daily-change-pct').textContent = '—';
        document.getElementById('pf-mood').textContent = '—';
    }}

    renderAllocChart(weightedAllocation(portfoy));
    renderRiskGauge(weightedRisk(portfoy));
    renderDailyPnlChart(portfoy);
}}

function render() {{
    const portfoy = getPortfoy();
    const kodlar = Object.keys(portfoy);
    if (!kodlar.length) {{ recalcAndRender(); return; }}
    Promise.all(kodlar.map(kod =>
        fetch('data/fon-kartlari/' + kod + '.json').then(r => r.ok ? r.json() : null).catch(() => null)
    )).then(results => {{
        fundsData = {{}};
        kodlar.forEach((kod, i) => {{
            const d = results[i];
            if (!d) return;
            const seri = d.fiyat_grafigi || [];
            d._sonFiyat = seri.length ? seri[seri.length - 1].value : null;
            d._oncekiFiyat = seri.length > 1 ? seri[seri.length - 2].value : null;
            d._sonTarih = seri.length ? seri[seri.length - 1].time : null;
            fundsData[kod] = d;
        }});
        recalcAndRender();
    }});
}}

document.getElementById('pf-add-input').addEventListener('change', function() {{
    const val = this.value.trim();
    if (!val) return;
    const kod = val.split(' — ')[0].toUpperCase();
    const portfoy = getPortfoy();
    if (portfoy[kod] !== undefined) {{
        alert('Bu fon zaten portföyünüzde bulunuyor: ' + kod);
        this.value = '';
        return;
    }}
    portfoy[kod] = 0;
    setPortfoy(portfoy);
    this.value = '';
    render();
}});

document.getElementById('pf-currency-tabs').querySelectorAll('.period-tab').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('#pf-currency-tabs .period-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currency = btn.dataset.c;
        recalcAndRender();
    }});
}});

fetch('data/fon-kartlari/_benchmarks.json').then(r => r.ok ? r.json() : {{}}).then(b => {{ benchmarks = b || {{}}; render(); }}).catch(() => {{ render(); }});
fetch('data/fon-kartlari/_index.json').then(r => r.ok ? r.json() : []).then(index => {{
    const list = document.getElementById('pf-add-list');
    list.innerHTML = index.map(f => '<option value="' + f.kod + ' — ' + (f.ad || '') + '">').join('');
}}).catch(() => {{}});
</script>"""

    with open("docs/portfoyum.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA — Portföyüm", "portfoyum.html", body))
    print("Portföyüm sayfası oluşturuldu: docs/portfoyum.html")


def main():
    df = pd.read_parquet(DATA_PATH)
    df['Tarih'] = pd.to_datetime(df['Tarih']).dt.normalize()
    # Veri hatası temizliği: bazı günlerde Fiyat=0 kaydedilmiş (TEFAS kesintisi).
    onceki_satir = len(df)
    df = df[df['Fiyat'] > 0]
    temizlenen = onceki_satir - len(df)
    if temizlenen:
        print(f"Veri temizliği: {temizlenen} satır (Fiyat<=0) veriden çıkarıldı.")
    df = df.sort_values(['Fon Kodu', 'Tarih'])

    mapping = pd.read_excel(MAPPING_PATH)
    fon_adlari = load_fon_adlari()
    if fon_adlari:
        # TEFAS'ın kendi güncel unvanını tercih et; eşleştirme dosyasındaki isim
        # sadece o fon TEFAS verisinde henüz yoksa yedek olarak kullanılır.
        mapping['Fon Adı'] = mapping['Fon Kodu'].map(fon_adlari).combine_first(mapping['Fon Adı'])
    acik_fon_kodlari = load_acik_fon_kodlari()

    res, anchor = build_fund_metrics(df)
    res = res.merge(mapping, on='Fon Kodu', how='left')
    res = res[res['Alt Kategori'].notna()]
    # Kapalı (TEFAS'a alım-satıma kapalı) fonlar puanlamaya HİÇ girmez: ne kendileri
    # skor alır, ne de kategori içi yüzdelik sıralamayı (pct_rank_within) etkiler.
    # Liste henüz toplanmadıysa (acik_fon_kodlari None) filtre uygulanmaz.
    if acik_fon_kodlari is not None:
        onceki = len(res)
        res = res[res['Fon Kodu'].isin(acik_fon_kodlari)]
        print(f"[skor] Kapalı fonlar puanlamadan çıkarıldı: {onceki - len(res)} fon "
              f"(kalan {len(res)} açık fon puanlanacak).")
    res = compute_scores(res)

    os.makedirs("docs", exist_ok=True)
    write_hareketler_page(df, mapping)
    write_category_summary(res, anchor)
    write_yeni_fonlar_page(df, mapping, fon_adlari, acik_fon_kodlari)
    write_favoriler_page(anchor)
    write_portfoyum_page(anchor)


if __name__ == "__main__":
    main()
