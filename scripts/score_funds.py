import pandas as pd
import numpy as np
import os

# ============================================================
# BU SATIRI ELLE GÜNCELLE: TLREF (Borsa İstanbul TL Referans Faiz Oranı)
# https://www.borsaistanbul.com/endeksler/tlref adresinden en son değeri al
RISK_FREE_RATE = 0.3999  # 17 Temmuz 2026 itibarıyla %39,99
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
    ('kategori-ozeti.html', 'Puanlama - Kategori Özeti'),
    ('tum-fonlar.html', 'Puanlama - Tüm Fonlar'),
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
.period-tabs { display: flex; gap: 6px; margin-bottom: 18px; }
.period-tab {
    padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
    background: var(--panel); color: var(--ink-dim); border: 1px solid var(--line);
}
.period-tab.active { background: var(--blue); color: white; border-color: var(--blue); }
.period-panel { display: none; }
.period-panel.active { display: block; }
footer { text-align: center; color: var(--ink-dim); font-size: 12px; margin-top: 24px; }
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
        return None
    try:
        df = pd.read_parquet(path, columns=["Fon Kodu"])
    except Exception:
        return None
    if df.empty:
        return None
    return set(df["Fon Kodu"])

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
                return '<option value="' + f.kod + '">' + f.kod + ' — ' + (f.ad || '') + '</option>';
            }).join('');
        })
        .catch(function() {});
    function go() {
        var raw = input.value.trim();
        if (!raw) return;
        var kod = raw.split(/[—-]/)[0].trim().toUpperCase();
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
<script>
if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('sw.js');
}}
</script>
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
# Sayfa 1: Tüm Fonlar (puanlama tablosu)
# ------------------------------------------------------------------

def write_tum_fonlar_page(res, anchor):
    cols = ['Fon Kodu', 'Fon Adı', 'Alt Kategori', 'Kategori_Sırası', 'TEFAS_Skoru',
            'Skor_Momentum', 'Skor_Getiri', 'Skor_ParaAkışı', 'Skor_Sharpe', 'Skor_StdDev',
            'Kullanılan_Bileşenler', 'Fon Toplam Değer']
    headers = ['Fon Kodu', 'Fon Adı', 'Alt Kategori', 'Kat. Sıra', 'Fonlarca Skoru',
               'Momentum', 'Getiri', 'Para Akışı', 'Sharpe', 'StdDev',
               'Kullanılan Bileşenler', 'Fon Toplam Değer']

    table = res[res['TEFAS_Skoru'].notna()].sort_values(
        ['Alt Kategori', 'TEFAS_Skoru'], ascending=[True, False])[cols].copy()
    table['Fon Adı'] = table['Fon Adı'].apply(kisalt_unvan)

    for c in ['TEFAS_Skoru', 'Skor_Momentum', 'Skor_Getiri', 'Skor_ParaAkışı', 'Skor_Sharpe', 'Skor_StdDev']:
        table[c] = table[c].round(1)
    table['Kategori_Sırası'] = table['Kategori_Sırası'].astype(int)
    table['Fon Toplam Değer'] = table['Fon Toplam Değer'].apply(lambda x: f"{x:,.0f}".replace(",", "."))
    table['Fon Kodu'] = table['Fon Kodu'].apply(fonlarca_link)
    table.columns = headers

    html_table = table.to_html(index=False, table_id="tefasTable", classes="display", escape=False, na_rep="—")

    extra_meta = (f'<span>Risksiz oran (TLREF): %{RISK_FREE_RATE*100:.2f}</span>'
                  f'<span>Toplam fon: {len(table)}</span>')
    body = f"""{page_header('tum-fonlar.html', 'Tüm Fonlar', anchor, extra_meta)}
<div class="card">
{html_table}
</div>
<footer>Kategori içi percentile bazlı puanlama · Momentum %35 · Getiri %25 · Para Akışı %15 · Sharpe %15 · StdDev %10</footer>
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/fixedcolumns/4.3.0/js/dataTables.fixedColumns.min.js"></script>
<script>
function scoreColor(v) {{
    if (v === null || v === "" || v === "—" || isNaN(v)) return null;
    v = parseFloat(v);
    if (v >= 75) return "rgba(76,187,109,0.22)";
    if (v >= 50) return "rgba(224,178,63,0.22)";
    return "rgba(224,90,90,0.22)";
}}
function scoreTextColor(v) {{
    if (v === null || v === "" || v === "—" || isNaN(v)) return null;
    v = parseFloat(v);
    if (v >= 75) return "#4cbb6d";
    if (v >= 50) return "#e0b23f";
    return "#e05a5a";
}}
$(document).ready(function() {{
    var tefasTable = $('#tefasTable').DataTable({{
        pageLength: 25,
        order: [[4, 'desc']],
        scrollX: true,
        scrollY: '65vh',
        scrollCollapse: true,
        fixedColumns: {{ start: 1 }},
        autoWidth: false,
        language: {{ url: 'https://cdn.datatables.net/plug-ins/1.13.6/i18n/tr.json' }},
        columnDefs: [
            {{ targets: 0, width: '70px' }},
            {{ targets: 1, width: '340px' }},
            {{ targets: 2, width: '130px' }},
            {{ targets: 3, width: '80px' }},
            {{ targets: 4, width: '95px' }},
            {{ targets: [5,6,7,8,9], width: '80px' }},
            {{ targets: 10, width: '220px' }},
            {{ targets: 11, width: '150px' }},
            {{ targets: [4,5,6,7,8,9], createdCell: function(td, cellData) {{
                var bg = scoreColor(cellData);
                var fg = scoreTextColor(cellData);
                if (bg) {{ $(td).html('<span class="score-badge" style="background:' + bg + ';color:' + fg + '">' + cellData + '</span>'); }}
            }} }}
        ]
    }});

    $(window).on('load', function() {{
        tefasTable.columns.adjust().draw(false);
    }});
}});
</script>"""
    extra_style = """
table.dataTable { font-size: 13px; }
table.dataTable th, table.dataTable td { white-space: nowrap; }
@media (min-width: 900px) {
  #tefasTable td:nth-child(2) { white-space: normal; overflow-wrap: break-word; line-height: 1.3; }
}
table.dataTable thead th {
    background: var(--panel) !important; color: var(--teal-bright); font-weight: 600; border-bottom: 2px solid var(--line) !important;
    padding: 10px 20px !important; text-align: left; cursor: pointer; background-image: none !important;
}
table.dataTable thead th.sorting:after,
table.dataTable thead th.sorting_asc:after,
table.dataTable thead th.sorting_desc:after {
    font-size: 11px; opacity: 0.6; margin-left: 6px;
}
table.dataTable thead th.sorting:after { content: "⇕"; }
table.dataTable thead th.sorting_asc:after { content: "▲"; opacity: 1; }
table.dataTable thead th.sorting_desc:after { content: "▼"; opacity: 1; }

/* DataTables'ın scrollX/scrollY icin olusturdugu gizli "genislik esitleme" basligi
   yukarıdaki !important kurallarindan etkilenip gorunur oluyordu - burada sifirliyoruz. */
.dataTables_scrollBody thead th, .dataTables_scrollBody thead td {
    padding: 0 !important; height: 0 !important; border: none !important;
    line-height: 0 !important; font-size: 0 !important;
}
.DTFC_LeftBodyLiner thead th, .DTFC_LeftBodyLiner thead td {
    padding: 0 !important; height: 0 !important; border: none !important;
    line-height: 0 !important; font-size: 0 !important;
}

table.dataTable tbody td { padding: 8px !important; vertical-align: middle; background: var(--card); color: var(--ink); border-bottom: 1px solid #2b2e37 !important; }
table.dataTable tbody tr:hover td { background: #1a1d25 !important; }
table.dataTable tbody td a { color: var(--teal-bright); font-weight: 600; text-decoration: underline; text-decoration-color: #3a6b68; }
table.dataTable tbody td a:hover { color: #6fd8cd; text-decoration-color: #6fd8cd; }
/* Dikey ızgara çizgilerini de ince ve gri yap */
table.dataTable { border-collapse: collapse !important; }
table.dataTable th, table.dataTable td { border-color: #2b2e37 !important; }
table.dataTable thead th { border-bottom: 1px solid #3a3d48 !important; }

/* Kolon hizalamaları: 1 Fon Kodu 2 Fon Adı(sol) 3 Alt Kategori(sol) 4 Kat.Sıra
   5 Fonlarca Skoru 6 Momentum 7 Getiri 8 Para Akışı 9 Sharpe 10 StdDev 11 Bileşenler(sol) 12 Fon Toplam Değer */
#tefasTable th:nth-child(1), #tefasTable td:nth-child(1),
#tefasTable th:nth-child(4), #tefasTable td:nth-child(4),
#tefasTable th:nth-child(5), #tefasTable td:nth-child(5),
#tefasTable th:nth-child(6), #tefasTable td:nth-child(6),
#tefasTable th:nth-child(7), #tefasTable td:nth-child(7),
#tefasTable th:nth-child(8), #tefasTable td:nth-child(8),
#tefasTable th:nth-child(9), #tefasTable td:nth-child(9),
#tefasTable th:nth-child(10), #tefasTable td:nth-child(10) {
    text-align: center;
}
#tefasTable th:nth-child(12) { text-align: left; }
#tefasTable td:nth-child(12) { text-align: right; }

/* DataTables FixedColumns dondurulmuş sütun klonu için aynı hizalama */
.DTFC_LeftHeadWrapper th:nth-child(1), .DTFC_LeftBodyWrapper td:nth-child(1) { text-align: center; }
.DTFC_LeftBodyWrapper td { background: var(--card); color: var(--ink); border-bottom: 1px solid #2b2e37 !important; }
.DTFC_LeftHeadWrapper th { background: var(--panel) !important; background-image: none !important; color: var(--teal-bright); }
/* Dondurulmuş Fon Kodu sütunundaki link koyu temada beyaz kalıyordu — düzelt */
.DTFC_LeftBodyWrapper td a { color: var(--teal-bright) !important; font-weight: 600; text-decoration: underline; text-decoration-color: #3a6b68; }
.DTFC_LeftBodyWrapper td a:hover { color: #6fd8cd !important; text-decoration-color: #6fd8cd; }

.dataTables_wrapper .dataTables_filter input, .dataTables_wrapper .dataTables_length select {
    border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px;
    background: var(--panel); color: var(--ink);
}
.dataTables_wrapper .dataTables_filter label, .dataTables_wrapper .dataTables_length label { color: var(--ink-dim); }
.dataTables_wrapper .dataTables_info { clear: both; margin-top: 10px; font-size: 13px; color: var(--ink-dim); }
.dataTables_wrapper .dataTables_paginate {
    display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; float: none !important;
}
.dataTables_wrapper .dataTables_paginate .paginate_button {
    padding: 6px 12px; margin: 0; border: 1px solid var(--line) !important; border-radius: 6px;
    cursor: pointer; color: var(--teal-bright) !important; background: var(--panel) !important;
}
.dataTables_wrapper .dataTables_paginate .paginate_button.current {
    background: var(--blue) !important; color: white !important; border-color: var(--blue) !important;
}
.dataTables_wrapper .dataTables_paginate .paginate_button:hover:not(.disabled) {
    background: #363a46 !important;
}
.dataTables_wrapper .dataTables_paginate .paginate_button.disabled {
    color: #5a606e !important; cursor: default; background: var(--panel) !important;
}
"""
    extra_head = ('<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">'
                  '<link rel="stylesheet" href="https://cdn.datatables.net/fixedcolumns/4.3.0/css/fixedColumns.dataTables.min.css">')
    with open("docs/tum-fonlar.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA — Tüm Fonlar", "tum-fonlar.html", body, extra_style, extra_head))
    print("Tüm Fonlar sayfası oluşturuldu: docs/tum-fonlar.html")


# ------------------------------------------------------------------
# Sayfa 2: Kategori Özeti
# ------------------------------------------------------------------

def write_category_summary(res, anchor):
    plot_df = res[res['TEFAS_Skoru'].notna()]
    sections = []
    for kat, g in plot_df.groupby('Alt Kategori', sort=True):
        if len(g) < 3:
            continue
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
<div class="card kat-card">
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

    body = f"""{page_header('kategori-ozeti.html', 'Kategori Özeti', anchor)}
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
    # Sadece TEFAS'a açık fonları göster (getFplFonList'ten gelen liste).
    # Liste henüz toplanmadıysa (acik_fon_kodlari None) filtre uygulanmaz.
    if acik_fon_kodlari is not None:
        yeni = yeni[yeni['Fon Kodu'].isin(acik_fon_kodlari)]
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
    res = compute_scores(res)

    os.makedirs("docs", exist_ok=True)
    write_hareketler_page(df, mapping)
    write_category_summary(res, anchor)
    write_tum_fonlar_page(res, anchor)
    write_yeni_fonlar_page(df, mapping, fon_adlari, acik_fon_kodlari)


if __name__ == "__main__":
    main()
