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
* { box-sizing: border-box; }
body {
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    margin: 0; padding: 32px 40px 60px; background: #f4f6f9; color: #1a1a1a;
}
.header {
    background: linear-gradient(135deg, #1F4E78 0%, #2c6ba0 100%);
    color: white; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}
.header h1 { margin: 0; font-size: 26px; font-weight: 600; }
.header .meta span { background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 20px; font-size: 13px; }
.card {
    background: white; border-radius: 12px; padding: 20px 24px 24px; margin-bottom: 18px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.kat-card h2 { margin: 0 0 4px 0; color: #1F4E78; font-size: 18px; }
.kat-count { color: #93a0b0; font-size: 13px; font-weight: 400; }
.kat-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 800px) { .kat-cols { grid-template-columns: 1fr; } }
h3 { font-size: 13px; margin: 0 0 8px 0; }
h3.up { color: #1a7a37; }
h3.down { color: #b3261e; }
table.mini { width: 100%; border-collapse: collapse; font-size: 13px; }
table.mini th { text-align: left; color: #93a0b0; font-weight: 500; padding: 4px 6px; border-bottom: 1px solid #eef2f7; }
table.mini td { padding: 5px 6px; border-bottom: 1px solid #f4f6f9; }
table.mini td a { color: #1F4E78; font-weight: 600; text-decoration: underline; text-decoration-color: #a9c3da; }
table.mini td a:hover { color: #14345a; text-decoration-color: #14345a; }
.score-badge { display: inline-block; min-width: 50px; padding: 2px 7px; border-radius: 6px; font-weight: 600; text-align: center; }
.score-badge.good { background: #c6efce; color: #14361f; }
.score-badge.bad { background: #ffc7ce; color: #5c1a1f; }
.period-tabs { display: flex; gap: 6px; margin-bottom: 18px; }
.period-tab {
    padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
    background: #eef2f7; color: #5f6b7a; border: none;
}
.period-tab.active { background: #1F4E78; color: white; }
.period-panel { display: none; }
.period-panel.active { display: block; }
footer { text-align: center; color: #93a0b0; font-size: 12px; margin-top: 24px; }
"""


def fonlarca_link(kod):
    return f'<a href="https://fonlarca.com/fon/{kod.lower()}.html" target="_blank">{kod}</a>'


def nav_bar(active):
    parts = []
    for href, label in NAV_PAGES:
        style = ("background:rgba(255,255,255,0.28); font-weight:600;" if href == active
                 else "background:rgba(255,255,255,0.12);")
        parts.append(f'<a href="{href}" style="color:white; text-decoration:none; padding:5px 14px; '
                     f'border-radius:20px; font-size:13px; {style}">{label}</a>')
    return '<div style="display:flex; gap:8px; margin-top:12px; flex-wrap:wrap;">' + ''.join(parts) + '</div>'


def page_header(active, subtitle, anchor, extra_meta=""):
    return f"""<div class="header">
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
        <img src="logo.jpg" alt="Fonlarca" style="height:36px; width:36px; border-radius:8px; object-fit:cover;">
        <h1>FONLARCA Puanlama Sistemi <span style="font-weight:400; opacity:0.75; font-size:16px;">— {subtitle}</span></h1>
    </div>
    <div class="meta"><span>Son güncelleme: {anchor.date()}</span>{extra_meta}</div>
    {nav_bar(active)}
</div>"""


def page_shell(title, active, body, extra_style=""):
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{BASE_STYLE}{extra_style}</style>
</head>
<body>
{body}
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
    cols = ['Alt Kategori', 'Kategori_Sırası', 'Fon Kodu', 'Fon Adı', 'TEFAS_Skoru',
            'Skor_Momentum', 'Skor_Getiri', 'Skor_ParaAkışı', 'Skor_Sharpe', 'Skor_StdDev',
            'Kullanılan_Bileşenler', 'Fon Toplam Değer']
    headers = ['Alt Kategori', 'Kat. Sıra', 'Fon Kodu', 'Fon Adı', 'TEFAS Skoru',
               'Momentum', 'Getiri', 'Para Akışı', 'Sharpe', 'StdDev',
               'Kullanılan Bileşenler', 'Fon Toplam Değer']

    table = res[res['TEFAS_Skoru'].notna()].sort_values(
        ['Alt Kategori', 'TEFAS_Skoru'], ascending=[True, False])[cols].copy()

    for c in ['TEFAS_Skoru', 'Skor_Momentum', 'Skor_Getiri', 'Skor_ParaAkışı', 'Skor_Sharpe', 'Skor_StdDev']:
        table[c] = table[c].round(1)
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
<script>
function scoreColor(v) {{
    if (v === null || v === "" || v === "—" || isNaN(v)) return null;
    v = parseFloat(v);
    if (v >= 75) return "#c6efce";
    if (v >= 50) return "#ffeb9c";
    return "#ffc7ce";
}}
$(document).ready(function() {{
    $('#tefasTable').DataTable({{
        pageLength: 25,
        order: [[4, 'desc']],
        language: {{ url: 'https://cdn.datatables.net/plug-ins/1.13.6/i18n/tr.json' }},
        columnDefs: [
            {{ targets: [4,5,6,7,8,9], createdCell: function(td, cellData) {{
                var bg = scoreColor(cellData);
                if (bg) {{ $(td).html('<span class="score-badge" style="background:' + bg + '">' + cellData + '</span>'); }}
            }} }}
        ]
    }});
}});
</script>"""
    extra_style = """
table.dataTable { font-size: 13px; border-collapse: collapse !important; width: 100% !important; }
table.dataTable thead th { background: #eef2f7; color: #1F4E78; font-weight: 600; border-bottom: 2px solid #d7e0ea !important; padding: 10px 8px !important; }
table.dataTable tbody td { padding: 8px !important; vertical-align: middle; }
table.dataTable tbody tr:hover { background: #f0f6fc !important; }
table.dataTable tbody td a { color: #1F4E78; font-weight: 600; text-decoration: underline; text-decoration-color: #a9c3da; }
table.dataTable tbody td a:hover { color: #14345a; text-decoration-color: #14345a; }
.dataTables_wrapper .dataTables_filter input, .dataTables_wrapper .dataTables_length select { border: 1px solid #d7e0ea; border-radius: 6px; padding: 4px 8px; }
"""
    with open("docs/tum-fonlar.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA Puanlama Sistemi — Tüm Fonlar", "tum-fonlar.html", body, extra_style))
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
                out += (f"<tr><td>{fonlarca_link(r['Fon Kodu'])}</td><td>{r['Fon Adı']}</td>"
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
        f.write(page_shell("FONLARCA Puanlama Sistemi — Kategori Özeti", "kategori-ozeti.html", body))
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


def _mover_rows(sub, value_col, fmt, cls):
    out = ""
    for _, r in sub.iterrows():
        out += (f"<tr><td>{fonlarca_link(r['Fon Kodu'])}</td><td>{r['Fon Adı']}</td>"
                f"<td><span class='score-badge {cls}'>{fmt(r[value_col])}</span></td></tr>")
    return out


def _mover_block(movers, value_col, fmt, title):
    valid = movers[movers[value_col].notna()]
    top5 = valid.sort_values(value_col, ascending=False).head(5)
    bottom5 = valid.sort_values(value_col, ascending=True).head(5)
    return f"""
<div>
    <h3 class="up">▲ En Çok Artan 5</h3>
    <table class="mini"><tr><th>Kod</th><th>Fon Adı</th><th>{title}</th></tr>{_mover_rows(top5, value_col, fmt, 'good')}</table>
</div>
<div>
    <h3 class="down">▼ En Çok Azalan 5</h3>
    <table class="mini"><tr><th>Kod</th><th>Fon Adı</th><th>{title}</th></tr>{_mover_rows(bottom5, value_col, fmt, 'bad')}</table>
</div>"""


def write_hareketler_page(df, mapping):
    periods = [('gunluk', 1, 'Günlük'), ('haftalik', 7, 'Haftalık'), ('aylik', 30, 'Aylık')]
    movers_by_key = {key: build_movers(df, mapping, days) for key, days, _ in periods}
    anchor = movers_by_key['gunluk'][1]

    def pct_fmt(v):
        return f"{v:+.2f}%"

    def kisi_fmt(v):
        return f"{v:+,.0f}".replace(",", ".")

    def tl_fmt(v):
        return f"{v:+,.0f}".replace(",", ".")

    metrics = [
        ('Fiyat Hareketleri', 'Fiyat_Değişim_%', pct_fmt, 'Değişim'),
        ('Yatırımcı Sayısı Hareketleri', 'Kişi_Değişim', kisi_fmt, 'Kişi'),
        ('Para Akışı Hareketleri (TL)', 'Net_Akış_TL', tl_fmt, 'TL'),
    ]

    tab_buttons = []
    panels = []
    for i, (key, days, label) in enumerate(periods):
        active_cls = "active" if i == 0 else ""
        tab_buttons.append(f'<button class="period-tab {active_cls}" onclick="showPeriod(\'{key}\')" id="tab-{key}">{label}</button>')

        movers, _ = movers_by_key[key]
        metric_cards = []
        for metric_title, col, fmt, unit_title in metrics:
            metric_cards.append(f"""
<div class="card kat-card">
    <h2>{metric_title}</h2>
    <div class="kat-cols">{_mover_block(movers, col, fmt, unit_title)}</div>
</div>""")
        panels.append(f'<div class="period-panel {active_cls}" id="panel-{key}">{"".join(metric_cards)}</div>')

    body = f"""{page_header('index.html', 'Hareketler', anchor)}
<div class="period-tabs">{''.join(tab_buttons)}</div>
{''.join(panels)}
<script>
function showPeriod(key) {{
    document.querySelectorAll('.period-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.period-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + key).classList.add('active');
    document.getElementById('tab-' + key).classList.add('active');
}}
</script>"""

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA Puanlama Sistemi — Hareketler", "index.html", body))
    print("Hareketler sayfası (açılış sayfası) oluşturuldu: docs/index.html")


# ------------------------------------------------------------------
# Sayfa 4: En Son Eklenen Fonlar
# ------------------------------------------------------------------

def write_yeni_fonlar_page(df, mapping):
    anchor = df['Tarih'].max()
    cutoff = anchor - pd.Timedelta(days=30)

    first_dates = df.groupby('Fon Kodu')['Tarih'].min().reset_index()
    first_dates.columns = ['Fon Kodu', 'İlk İşlem Tarihi']
    yeni = first_dates[first_dates['İlk İşlem Tarihi'] >= cutoff].copy()
    yeni = yeni.merge(mapping[['Fon Kodu', 'Fon Adı', 'Alt Kategori']], on='Fon Kodu', how='left')
    yeni = yeni[yeni['Alt Kategori'].notna()]
    yeni = yeni.sort_values('İlk İşlem Tarihi', ascending=False)

    rows = ""
    for _, r in yeni.iterrows():
        rows += (f"<tr><td>{fonlarca_link(r['Fon Kodu'])}</td><td>{r['Fon Adı']}</td>"
                 f"<td>{r['Alt Kategori']}</td><td>{r['İlk İşlem Tarihi'].date()}</td></tr>")

    table_html = f"""<table class="mini" style="font-size:14px;">
<tr><th>Kod</th><th>Fon Adı</th><th>Alt Kategori</th><th>İlk İşlem Tarihi</th></tr>
{rows if rows else '<tr><td colspan="4" style="color:#93a0b0; padding:16px;">Son 30 günde yeni eklenen fon bulunamadı.</td></tr>'}
</table>"""

    body = f"""{page_header('yeni-fonlar.html', 'En Son Eklenen Fonlar', anchor)}
<div class="card">
    <h2 style="color:#1F4E78; margin-top:0;">Son 30 Günde İlk Kez Fiyat Üreten Fonlar <span class="kat-count">({len(yeni)} fon)</span></h2>
    {table_html}
</div>"""

    with open("docs/yeni-fonlar.html", "w", encoding="utf-8") as f:
        f.write(page_shell("FONLARCA Puanlama Sistemi — En Son Eklenen Fonlar", "yeni-fonlar.html", body))
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

    res, anchor = build_fund_metrics(df)
    res = res.merge(mapping, on='Fon Kodu', how='left')
    res = res[res['Alt Kategori'].notna()]
    res = compute_scores(res)

    os.makedirs("docs", exist_ok=True)
    write_hareketler_page(df, mapping)
    write_category_summary(res, anchor)
    write_tum_fonlar_page(res, anchor)
    write_yeni_fonlar_page(df, mapping)


if __name__ == "__main__":
    main()
