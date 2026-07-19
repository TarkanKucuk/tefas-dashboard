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
OUTPUT_HTML = "docs/tum-fonlar.html"

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
    # Para Akışı: kategori içindeki toplam akış hareketine göre pay
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


def fonlarca_link(kod):
    return f'<a href="https://fonlarca.com/fon/{kod.lower()}.html" target="_blank">{kod}</a>'


def write_html(res, anchor):
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

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TEFAS Puanlama Sistemi</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>
* {{ box-sizing: border-box; }}
body {{
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    margin: 0;
    padding: 32px 40px 60px;
    background: #f4f6f9;
    color: #1a1a1a;
}}
.header {{
    background: linear-gradient(135deg, #1F4E78 0%, #2c6ba0 100%);
    color: white;
    padding: 28px 32px;
    border-radius: 12px;
    margin-bottom: 24px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}}
.header h1 {{ margin: 0 0 8px 0; font-size: 26px; font-weight: 600; }}
.header .meta {{ font-size: 13px; opacity: 0.9; display: flex; gap: 20px; flex-wrap: wrap; }}
.header .meta span {{ background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 20px; }}
.card {{
    background: white;
    border-radius: 12px;
    padding: 20px 24px 28px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    overflow-x: auto;
}}
table.dataTable {{
    font-size: 13px;
    border-collapse: collapse !important;
    width: 100% !important;
}}
table.dataTable thead th {{
    background: #eef2f7;
    color: #1F4E78;
    font-weight: 600;
    border-bottom: 2px solid #d7e0ea !important;
    padding: 10px 8px !important;
}}
table.dataTable tbody td {{ padding: 8px !important; vertical-align: middle; }}
table.dataTable tbody td a {{ color: #1F4E78; font-weight: 600; text-decoration: none; }}
table.dataTable tbody td a:hover {{ text-decoration: underline; }}
table.dataTable tbody tr:hover {{ background: #f0f6fc !important; }}
.score-badge {{
    display: inline-block;
    min-width: 42px;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 600;
    text-align: center;
    color: #14361f;
}}
.dataTables_wrapper .dataTables_filter input,
.dataTables_wrapper .dataTables_length select {{
    border: 1px solid #d7e0ea;
    border-radius: 6px;
    padding: 4px 8px;
}}
footer {{ text-align: center; color: #93a0b0; font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
<div class="header">
    <h1>TEFAS Puanlama Sistemi</h1>
    <div class="meta">
        <span>Son güncelleme: {anchor.date()}</span>
        <span>Risksiz oran (TLREF): %{RISK_FREE_RATE*100:.2f}</span>
        <span>Toplam fon: {len(table)}</span>
        <span><a href="index.html" style="color:white; text-decoration: underline;">← Kategori Özeti</a></span>
    </div>
</div>
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
</script>
</body>
</html>"""

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML raporu oluşturuldu:", OUTPUT_HTML)


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

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TEFAS Kategori Özeti</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    margin: 0; padding: 32px 40px 60px; background: #f4f6f9; color: #1a1a1a;
}}
.header {{
    background: linear-gradient(135deg, #1F4E78 0%, #2c6ba0 100%);
    color: white; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}}
.header h1 {{ margin: 0 0 8px 0; font-size: 26px; font-weight: 600; }}
.header .meta span {{ background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 20px; font-size: 13px; }}
.header a {{ color: white; text-decoration: underline; }}
.card {{
    background: white; border-radius: 12px; padding: 20px 24px 24px; margin-bottom: 18px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}}
.kat-card h2 {{ margin: 0 0 14px 0; color: #1F4E78; font-size: 18px; }}
.kat-count {{ color: #93a0b0; font-size: 13px; font-weight: 400; }}
.kat-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
@media (max-width: 800px) {{ .kat-cols {{ grid-template-columns: 1fr; }} }}
h3 {{ font-size: 13px; margin: 0 0 8px 0; }}
h3.up {{ color: #1a7a37; }}
h3.down {{ color: #b3261e; }}
table.mini {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
table.mini th {{ text-align: left; color: #93a0b0; font-weight: 500; padding: 4px 6px; border-bottom: 1px solid #eef2f7; }}
table.mini td {{ padding: 5px 6px; border-bottom: 1px solid #f4f6f9; }}
table.mini td a {{ color: #1F4E78; font-weight: 600; text-decoration: none; }}
table.mini td a:hover {{ text-decoration: underline; }}
.score-badge {{ display: inline-block; min-width: 36px; padding: 2px 7px; border-radius: 6px; font-weight: 600; text-align: center; }}
.score-badge.good {{ background: #c6efce; color: #14361f; }}
.score-badge.bad {{ background: #ffc7ce; color: #5c1a1f; }}
</style>
</head>
<body>
<div class="header">
    <h1>Kategori Özeti</h1>
    <div class="meta">
        <span>Son güncelleme: {anchor.date()}</span>
        <a href="tum-fonlar.html">Tüm Fonlar Tablosu →</a>
    </div>
</div>
{''.join(sections)}
</body>
</html>"""

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Kategori özeti (açılış sayfası) oluşturuldu: docs/index.html")


def main():
    df = pd.read_parquet(DATA_PATH)
    df['Tarih'] = pd.to_datetime(df['Tarih']).dt.normalize()
    # Veri hatası temizliği: bazı günlerde Fiyat=0 kaydedilmiş (TEFAS kesintisi).
    # Bu satırlar günlük getiri hesaplarını sonsuza (inf) sıçratıp Sharpe/StdDev'i bozuyor.
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
    write_html(res, anchor)
    write_category_summary(res, anchor)


if __name__ == "__main__":
    main()
