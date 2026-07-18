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
OUTPUT_HTML = "docs/index.html"

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


def write_html(res, anchor):
    cols = ['Alt Kategori', 'Kategori_Sırası', 'Fon Kodu', 'Fon Adı', 'TEFAS_Skoru',
            'Skor_Momentum', 'Skor_Getiri', 'Skor_ParaAkışı', 'Skor_Sharpe', 'Skor_StdDev',
            'Kullanılan_Bileşenler', 'Fon Toplam Değer', 'Son Tarih']
    table = res[res['TEFAS_Skoru'].notna()].sort_values(
        ['Alt Kategori', 'TEFAS_Skoru'], ascending=[True, False])[cols].copy()

    for c in ['TEFAS_Skoru', 'Skor_Momentum', 'Skor_Getiri', 'Skor_ParaAkışı', 'Skor_Sharpe', 'Skor_StdDev']:
        table[c] = table[c].round(1)
    table['Son Tarih'] = table['Son Tarih'].dt.strftime('%Y-%m-%d')

    html_table = table.to_html(index=False, table_id="tefasTable", classes="display", escape=True)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>TEFAS Puanlama Sistemi</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1 {{ color: #1F4E78; }}
.updated {{ color: #666; font-size: 0.9em; margin-bottom: 15px; }}
table.dataTable {{ font-size: 0.85em; }}
</style>
</head>
<body>
<h1>TEFAS Puanlama Sistemi</h1>
<p class="updated">Son güncelleme: {anchor.date()} | Risksiz oran (TLREF): %{RISK_FREE_RATE*100:.2f}
| Toplam fon: {len(table)}</p>
{html_table}
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
<script>
$(document).ready(function() {{
    $('#tefasTable').DataTable({{ pageLength: 25, order: [[4, 'desc']] }});
}});
</script>
</body>
</html>"""

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML raporu oluşturuldu:", OUTPUT_HTML)


def main():
    df = pd.read_parquet(DATA_PATH)
    df['Tarih'] = pd.to_datetime(df['Tarih'])
    df = df.sort_values(['Fon Kodu', 'Tarih'])

    mapping = pd.read_excel(MAPPING_PATH)

    res, anchor = build_fund_metrics(df)
    res = res.merge(mapping, on='Fon Kodu', how='left')
    res = res[res['Alt Kategori'].notna()]

    res = compute_scores(res)
    write_html(res, anchor)


if __name__ == "__main__":
    main()
