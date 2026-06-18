"""
streamlit_app/pages/3_Analytics.py — Deep analytics & charts
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database.db import init_pool, get_cursor

st.set_page_config(page_title="Analytics", page_icon="📊", layout="wide")
init_pool()

st.title("📊 Deep Analytics")

@st.cache_data(ttl=120)
def load_full_data(days: int = 7):
    with get_cursor() as cur:
        cur.execute("""
            SELECT na.headline, na.source, na.category, na.publish_date, na.scraped_at,
                   aa.sentiment_label, aa.sentiment_score, aa.market_direction,
                   aa.market_impact_score, aa.mentioned_tickers, aa.mentioned_sectors,
                   aa.key_topics
            FROM news_articles na
            LEFT JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '%s days'
            ORDER BY na.scraped_at DESC
        """, (days,))
        return pd.DataFrame([dict(r) for r in cur.fetchall()])

days = st.slider("Analysis window (days)", 1, 30, 7)
df = load_full_data(days)

if df.empty:
    st.warning("No data available yet.")
    st.stop()

df["publish_date"] = pd.to_datetime(df["publish_date"], utc=True, errors="coerce")
df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce")
df["market_impact_score"] = pd.to_numeric(df["market_impact_score"], errors="coerce")

st.markdown(f"**{len(df):,} articles** analysed over the last {days} days")

# ── Impact distribution ───────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.subheader("Impact Score Distribution")
    fig = px.histogram(df.dropna(subset=["market_impact_score"]),
                       x="market_impact_score", nbins=20,
                       color="market_direction",
                       color_discrete_map={"BULLISH":"#00ff88","BEARISH":"#ff4444","NEUTRAL":"#888"},
                       template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Sentiment by Source")
    src_df = df.groupby("source")["sentiment_score"].mean().reset_index()
    src_df.columns = ["source", "avg_sentiment"]
    fig2 = px.bar(src_df, x="source", y="avg_sentiment",
                  color="avg_sentiment", color_continuous_scale="RdYlGn",
                  template="plotly_dark", range_color=[-1, 1])
    st.plotly_chart(fig2, use_container_width=True)

# ── Sentiment over time ───────────────────────────────────────────────────────
st.subheader("Sentiment Trend Over Time")
if "publish_date" in df.columns:
    ts = df.dropna(subset=["publish_date", "sentiment_score"]).copy()
    ts["date"] = ts["publish_date"].dt.date
    daily = ts.groupby(["date", "sentiment_label"]).size().reset_index(name="count")
    fig3 = px.line(
        ts.groupby("date")["sentiment_score"].mean().reset_index(),
        x="date", y="sentiment_score", template="plotly_dark",
        labels={"sentiment_score": "Avg Sentiment (-1 to 1)"},
    )
    fig3.add_hline(y=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig3, use_container_width=True)

# ── Category breakdown ────────────────────────────────────────────────────────
col3, col4 = st.columns(2)
with col3:
    st.subheader("Articles by Category")
    cat_df = df["category"].value_counts().head(10).reset_index()
    cat_df.columns = ["category", "count"]
    fig4 = px.pie(cat_df, values="count", names="category",
                  template="plotly_dark", hole=0.3)
    st.plotly_chart(fig4, use_container_width=True)

with col4:
    st.subheader("Bullish vs Bearish by Source")
    bb = df[df["market_direction"].isin(["BULLISH","BEARISH"])].groupby(
        ["source","market_direction"]).size().reset_index(name="count")
    fig5 = px.bar(bb, x="source", y="count", color="market_direction",
                  color_discrete_map={"BULLISH":"#00ff88","BEARISH":"#ff4444"},
                  barmode="group", template="plotly_dark")
    st.plotly_chart(fig5, use_container_width=True)

# ── Scatter: impact vs sentiment ──────────────────────────────────────────────
st.subheader("Market Impact vs Sentiment Score")
scat = df.dropna(subset=["sentiment_score","market_impact_score"])
fig6 = px.scatter(scat, x="sentiment_score", y="market_impact_score",
                  color="market_direction", hover_data=["headline","source"],
                  color_discrete_map={"BULLISH":"#00ff88","BEARISH":"#ff4444","NEUTRAL":"#888"},
                  template="plotly_dark", opacity=0.7)
fig6.add_vline(x=0, line_dash="dash", line_color="gray")
st.plotly_chart(fig6, use_container_width=True)
