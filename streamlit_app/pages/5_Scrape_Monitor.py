"""
streamlit_app/pages/5_Scrape_Monitor.py
Monitor scraping pipeline health — run history, success rates, article counts.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database.db import init_pool, get_cursor

st.set_page_config(page_title="Scrape Monitor", page_icon="🕷️", layout="wide")

@st.cache_resource
def _init():
    init_pool()
_init()

st.title("🕷️ Scrape Pipeline Monitor")
st.markdown("Real-time health dashboard for all scraping sources.")

with st.sidebar:
    days = st.selectbox("Time window", [1, 3, 7], index=1,
                        format_func=lambda d: f"Last {d} day{'s' if d>1 else ''}")
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# ── Data ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_runs(days: int) -> pd.DataFrame:
    with get_cursor() as cur:
        cur.execute("""
            SELECT source, run_start, run_end, articles_found,
                   articles_new, status, error_message
            FROM scrape_runs
            WHERE run_start >= NOW() - INTERVAL '%s days'
            ORDER BY run_start DESC
            LIMIT 500
        """, (days,))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["run_start"] = pd.to_datetime(df["run_start"], utc=True, errors="coerce")
    df["run_end"]   = pd.to_datetime(df["run_end"],   utc=True, errors="coerce")
    df["duration_sec"] = (df["run_end"] - df["run_start"]).dt.total_seconds()
    return df

@st.cache_data(ttl=30)
def load_article_counts() -> pd.DataFrame:
    with get_cursor() as cur:
        cur.execute("""
            SELECT source,
                   COUNT(*) AS total,
                   COUNT(*) FILTER(WHERE scraped_at >= NOW() - INTERVAL '24 hours') AS last_24h,
                   COUNT(*) FILTER(WHERE scraped_at >= NOW() - INTERVAL '1 hour')   AS last_1h,
                   MAX(scraped_at) AS last_scraped
            FROM news_articles
            GROUP BY source
            ORDER BY total DESC
        """)
        rows = cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

df_runs = load_runs(days)
df_counts = load_article_counts()

# ── Article counts per source ─────────────────────────────────────────────────
st.subheader("📊 Article Coverage by Source")
if not df_counts.empty:
    df_counts["last_scraped"] = pd.to_datetime(df_counts["last_scraped"], utc=True, errors="coerce")
    df_counts["last_scraped_str"] = df_counts["last_scraped"].dt.strftime("%Y-%m-%d %H:%M UTC")

    cols = st.columns(len(df_counts))
    for i, (_, row) in enumerate(df_counts.iterrows()):
        with cols[i]:
            st.metric(
                label=row["source"],
                value=f"{int(row['total']):,}",
                delta=f"+{int(row['last_24h'])} today"
            )
            st.caption(f"Last: {row['last_scraped_str']}")
else:
    st.info("No articles scraped yet.")

st.markdown("---")

# ── Run history charts ────────────────────────────────────────────────────────
if df_runs.empty:
    st.info("No scrape run history found.")
    st.stop()

col1, col2 = st.columns(2)

with col1:
    st.subheader("New Articles per Run (by Source)")
    fig = px.bar(
        df_runs, x="run_start", y="articles_new", color="source",
        template="plotly_dark", barmode="stack",
        labels={"articles_new": "New Articles", "run_start": "Run Time"},
    )
    fig.update_layout(height=320, xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Success vs Failed Runs")
    status_counts = df_runs["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    color_map = {"SUCCESS": "#00ff88", "FAILED": "#ff4444", "RUNNING": "#f39c12"}
    fig2 = px.pie(status_counts, values="count", names="status",
                  color="status", color_discrete_map=color_map,
                  template="plotly_dark", hole=0.4)
    fig2.update_layout(height=320)
    st.plotly_chart(fig2, use_container_width=True)

# ── Source reliability ────────────────────────────────────────────────────────
st.subheader("📈 Source Reliability")
reliability = (
    df_runs.groupby("source")
    .agg(
        total_runs=("status", "count"),
        success_runs=("status", lambda x: (x == "SUCCESS").sum()),
        avg_new_articles=("articles_new", "mean"),
        avg_duration=("duration_sec", "mean"),
    )
    .reset_index()
)
reliability["success_rate"] = (reliability["success_runs"] / reliability["total_runs"] * 100).round(1)
reliability["avg_new_articles"] = reliability["avg_new_articles"].round(1)
reliability["avg_duration_min"] = (reliability["avg_duration"] / 60).round(1)

def _colour_rate(val):
    if pd.isna(val):
        return ""
    if val >= 90:
        return "color: #00ff88"
    elif val >= 70:
        return "color: #f39c12"
    return "color: #ff4444"

st.dataframe(
    reliability[["source","total_runs","success_runs","success_rate",
                 "avg_new_articles","avg_duration_min"]]
    .rename(columns={
        "source": "Source", "total_runs": "Total Runs",
        "success_runs": "Successful", "success_rate": "Success Rate (%)",
        "avg_new_articles": "Avg New Articles", "avg_duration_min": "Avg Duration (min)"
    })
    .style.applymap(_colour_rate, subset=["Success Rate (%)"]),
    use_container_width=True,
)

# ── Recent run log ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🗒️ Recent Run Log")
recent = df_runs.head(50).copy()
recent["run_start"] = recent["run_start"].dt.strftime("%Y-%m-%d %H:%M UTC")
recent["duration"]  = recent["duration_sec"].apply(
    lambda s: f"{int(s//60)}m {int(s%60)}s" if pd.notnull(s) else "-"
)

def _colour_status(val):
    return {"SUCCESS":"color:#00ff88","FAILED":"color:#ff4444","RUNNING":"color:#f39c12"}.get(val,"")

st.dataframe(
    recent[["run_start","source","status","articles_found","articles_new","duration"]]
    .style.applymap(_colour_status, subset=["status"]),
    use_container_width=True,
    height=400,
)

# ── Failed runs detail ────────────────────────────────────────────────────────
failed = df_runs[df_runs["status"] == "FAILED"]
if not failed.empty:
    st.markdown("---")
    st.subheader(f"⚠️ Failed Runs ({len(failed)})")
    for _, row in failed.iterrows():
        with st.expander(f"❌ {row['source']} — {row['run_start']}"):
            if row.get("error_message"):
                st.error(row["error_message"])
