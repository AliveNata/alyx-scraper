# -*- coding: utf-8 -*-
"""
Alyx Scraper - Streamlit Analytics Dashboard
Run: streamlit run analytics.py
"""
import json, os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

AUDIT_FILE = os.path.join(os.path.dirname(__file__), 'audit_log.json')

st.set_page_config(
    page_title='Alyx Analytics',
    page_icon='📊',
    layout='wide',
)

st.markdown("""
<style>
[data-testid="stMetricDelta"] svg { display: none; }
.metric-card { background: #f8fafc; border-radius: 10px; padding: 16px; text-align: center; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=30)
def load_data():
    if not os.path.exists(AUDIT_FILE):
        return pd.DataFrame()
    with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df['started_at'] = pd.to_datetime(df['started_at'], errors='coerce')
    df['date'] = df['started_at'].dt.date
    df['results'] = pd.to_numeric(df.get('results', 0), errors='coerce').fillna(0).astype(int)
    df['duration_s'] = pd.to_numeric(df.get('duration_s'), errors='coerce')
    return df


def period_count(df, col, days_back, days_from=0):
    now = datetime.now()
    cutoff_end   = now - timedelta(days=days_from)
    cutoff_start = now - timedelta(days=days_back)
    mask = (df[col] >= cutoff_start) & (df[col] < cutoff_end)
    return int(mask.sum())


def pct_change(cur, prev):
    if prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def delta_str(pct):
    if pct is None:
        return 'N/A', None
    sign = '+' if pct >= 0 else ''
    return f'{sign}{pct}%', 'normal' if pct >= 0 else 'inverse'


# ── Load ───────────────────────────────────────────────────────────────
df = load_data()

st.title('📊 Alyx Scraper — Analytics')

if df.empty:
    st.info('Belum ada data audit. Mulai scraping untuk melihat analytics.')
    st.stop()

now = datetime.now()

# ── KPI row ────────────────────────────────────────────────────────────
total_sessions = len(df)
total_results  = int(df['results'].sum())
today_sessions = int((df['date'] == now.date()).sum())
avg_duration   = round(df['duration_s'].dropna().mean(), 1) if not df['duration_s'].dropna().empty else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric('Total Sesi', total_sessions)
col2.metric('Total Hasil', total_results)
col3.metric('Sesi Hari Ini', today_sessions)
col4.metric('Avg Durasi (s)', avg_duration)

st.divider()

# ── Comparison: WoW / MoM / QoQ / YoY ────────────────────────────────
st.subheader('📈 Perbandingan Periode')

periods = [
    ('WoW', 7,   14),
    ('MoM', 30,  60),
    ('QoQ', 90,  180),
    ('YoY', 365, 730),
]

cols = st.columns(4)
for i, (label, cur_days, prev_days) in enumerate(periods):
    cur  = period_count(df, 'started_at', cur_days)
    prev = period_count(df, 'started_at', prev_days, days_from=cur_days)
    pct  = pct_change(cur, prev)
    d_str, d_dir = delta_str(pct)
    cols[i].metric(
        label=label,
        value=cur,
        delta=f'{d_str} vs prev period',
        delta_color=d_dir or 'off',
        help=f'Current {cur_days}d: {cur} | Prior {cur_days}d: {prev}',
    )

st.divider()

# ── Daily sessions line chart ──────────────────────────────────────────
st.subheader('📅 Penggunaan Harian')

chart_range = st.selectbox('Rentang waktu', ['7 Hari', '30 Hari', '90 Hari', 'Semua'], index=1)
days_map = {'7 Hari': 7, '30 Hari': 30, '90 Hari': 90, 'Semua': 9999}
n_days = days_map[chart_range]
cutoff = now - timedelta(days=n_days)

df_range = df[df['started_at'] >= cutoff].copy()

daily = df_range.groupby('date').agg(
    sessions=('date', 'count'),
    results=('results', 'sum'),
).reset_index()
daily['date'] = pd.to_datetime(daily['date'])
daily = daily.sort_values('date')

metric_choice = st.radio('Metrik', ['Sesi', 'Hasil'], horizontal=True)
y_col = 'sessions' if metric_choice == 'Sesi' else 'results'
y_label = 'Jumlah Sesi' if metric_choice == 'Sesi' else 'Jumlah Hasil'

fig = px.line(
    daily, x='date', y=y_col,
    labels={'date': 'Tanggal', y_col: y_label},
    markers=True,
    color_discrete_sequence=['#6366f1'],
)
fig.update_traces(line_width=2, marker_size=5)
fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)',
    xaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,.06)'),
    yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,.06)', rangemode='tozero'),
    height=320,
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Platform distribution ──────────────────────────────────────────────
st.subheader('🌐 Distribusi Platform')

all_platforms = []
for row in df.get('platforms', pd.Series(dtype=object)).dropna():
    if isinstance(row, list):
        all_platforms.extend(row)
    elif isinstance(row, str):
        all_platforms.append(row)

if all_platforms:
    plat_s = pd.Series(all_platforms).value_counts().reset_index()
    plat_s.columns = ['Platform', 'Count']
    fig2 = px.bar(
        plat_s, x='Platform', y='Count',
        color_discrete_sequence=['#6366f1'],
        labels={'Count': 'Jumlah Sesi'},
    )
    fig2.update_layout(
        margin=dict(l=0,r=0,t=10,b=0),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,.06)'),
        height=280,
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info('Belum ada data platform.')

st.divider()

# ── Top keywords ───────────────────────────────────────────────────────
st.subheader('🔑 Keyword Terpopuler')

all_kw = []
for row in df.get('keywords', pd.Series(dtype=object)).dropna():
    if isinstance(row, list):
        all_kw.extend(row)
    elif isinstance(row, str):
        all_kw.append(row)

if all_kw:
    kw_s = pd.Series(all_kw).value_counts().head(20).reset_index()
    kw_s.columns = ['Keyword', 'Count']
    fig3 = px.bar(
        kw_s, x='Count', y='Keyword', orientation='h',
        color_discrete_sequence=['#8b5cf6'],
    )
    fig3.update_layout(
        margin=dict(l=0,r=0,t=10,b=0),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(autorange='reversed'),
        height=max(200, len(kw_s)*28),
    )
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info('Belum ada data keyword.')

st.divider()

# ── Raw table ──────────────────────────────────────────────────────────
with st.expander('📋 Raw Audit Log'):
    display_cols = [c for c in ['started_at','ip','keywords','platforms','location','duration_s','results','status'] if c in df.columns]
    st.dataframe(df[display_cols].sort_values('started_at', ascending=False), use_container_width=True)

st.caption('Data di-refresh otomatis setiap 30 detik. Sumber: audit_log.json')
