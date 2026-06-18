"""
streamlit_app/app.py — Finance AI News & Trend Monitoring Dashboard
Run: streamlit run streamlit_app/app.py
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.db import (
    init_pool,
    get_recent_articles_with_analysis,
    get_trending_topics,
    get_cursor,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "Finance AI Monitor",
    page_icon   = "📈",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

# ── Init DB pool ──────────────────────────────────────────────────────────────
@st.cache_resource
def _init_db():
    init_pool()

_init_db()

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .bullish { color: #00ff88 !important; }
    .bearish { color: #ff4444 !important; }
    .neutral { color: #aaaaaa !important; }
    .news-card {
        background: #1a1a2e;
        border-left: 4px solid #0f3460;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 12px;
    }
    .news-card.positive { border-left-color: #00ff88; }
    .news-card.negative { border-left-color: #ff4444; }
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
    }
    .badge-positive { background: #003320; color: #00ff88; }
    .badge-negative { background: #330000; color: #ff4444; }
    .badge-neutral  { background: #222; color: #aaa; }
    .badge-bullish  { background: #003320; color: #00ff88; }
    .badge-bearish  { background: #330000; color: #ff4444; }
</style>
""", unsafe_allow_html=True)


# ── Data loaders (cached with TTL) ────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_articles(hours: int = 24, limit: int = 300) -> pd.DataFrame:
    rows = get_recent_articles_with_analysis(hours=hours, limit=limit)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "publish_date" in df.columns:
        df["publish_date"] = pd.to_datetime(df["publish_date"], utc=True, errors="coerce")
    for col in ("sentiment_score", "market_impact_score"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=120)
def load_trending(hours: int = 6) -> pd.DataFrame:
    rows = get_trending_topics(hours=hours, limit=20)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_hourly_stats() -> pd.DataFrame:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                date_trunc('hour', na.scraped_at)  AS hour,
                COUNT(*)                            AS count,
                AVG(aa.sentiment_score)             AS avg_sentiment,
                SUM(CASE WHEN aa.market_direction='BULLISH' THEN 1 ELSE 0 END) AS bullish,
                SUM(CASE WHEN aa.market_direction='BEARISH' THEN 1 ELSE 0 END) AS bearish
            FROM news_articles na
            LEFT JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '48 hours'
            GROUP BY hour
            ORDER BY hour
            """
        )
        rows = cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_source_stats() -> pd.DataFrame:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT na.source,
                   COUNT(*)                            AS articles,
                   AVG(aa.sentiment_score)             AS avg_sentiment,
                   AVG(aa.market_impact_score)         AS avg_impact,
                   COUNT(*) FILTER(WHERE aa.market_direction='BULLISH') AS bullish,
                   COUNT(*) FILTER(WHERE aa.market_direction='BEARISH') AS bearish
            FROM news_articles na
            LEFT JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '24 hours'
            GROUP BY na.source
            ORDER BY articles DESC
            """
        )
        rows = cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/stock-market.png", width=60)
    st.title("Finance AI Monitor")
    st.markdown("---")

    time_window = st.selectbox("Time Window", [6, 12, 24, 48, 72], index=2,
                               format_func=lambda x: f"Last {x}h")

    st.markdown("### Filters")
    sources_input = st.multiselect(
        "Sources",
        ["Reuters", "Yahoo Finance", "CNBC", "Bloomberg", "MarketWatch", "Investing.com"],
        default=[],
    )
    sentiment_filter = st.selectbox("Sentiment", ["All", "POSITIVE", "NEGATIVE", "NEUTRAL"])
    direction_filter = st.selectbox("Market Direction", ["All", "BULLISH", "BEARISH", "NEUTRAL"])
    min_impact = st.slider("Min Impact Score", 0, 100, 0)
    search_query = st.text_input("🔍 Search headlines...", "")

    st.markdown("---")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Last refresh: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")


# ── Load data ─────────────────────────────────────────────────────────────────

df_all     = load_articles(hours=time_window, limit=500)
df_trend   = load_trending(hours=min(time_window, 6))
df_hourly  = load_hourly_stats()
df_sources = load_source_stats()

# Apply filters
df = df_all.copy()
if not df.empty:
    if sources_input:
        df = df[df["source"].isin(sources_input)]
    if sentiment_filter != "All" and "sentiment_label" in df.columns:
        df = df[df["sentiment_label"] == sentiment_filter]
    if direction_filter != "All" and "market_direction" in df.columns:
        df = df[df["market_direction"] == direction_filter]
    if min_impact > 0 and "market_impact_score" in df.columns:
        df = df[df["market_impact_score"] >= min_impact]
    if search_query and "headline" in df.columns:
        df = df[df["headline"].str.contains(search_query, case=False, na=False)]


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# 📈 Finance AI News & Trend Monitor")
st.markdown(f"*Real-time intelligence platform — showing last {time_window} hours*")
st.markdown("---")


# ── KPI Metrics ───────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5, col6 = st.columns(6)

total = len(df)
positive = int((df["sentiment_label"] == "POSITIVE").sum()) if "sentiment_label" in df.columns else 0
negative = int((df["sentiment_label"] == "NEGATIVE").sum()) if "sentiment_label" in df.columns else 0
bullish  = int((df["market_direction"] == "BULLISH").sum()) if "market_direction" in df.columns else 0
bearish  = int((df["market_direction"] == "BEARISH").sum()) if "market_direction" in df.columns else 0
avg_impact = df["market_impact_score"].mean() if "market_impact_score" in df.columns and len(df) else 0

col1.metric("📰 Total Articles", total)
col2.metric("🟢 Positive",  positive, f"{round(positive/total*100)}%" if total else "0%")
col3.metric("🔴 Negative",  negative, f"{round(negative/total*100)}%" if total else "0%")
col4.metric("🐂 Bullish",   bullish)
col5.metric("🐻 Bearish",   bearish)
col6.metric("⚡ Avg Impact", f"{avg_impact:.1f}")

st.markdown("---")


# ── Charts Row 1 ──────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("📊 Hourly Article Volume & Sentiment")
    if not df_hourly.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_hourly["hour"], y=df_hourly["count"],
            name="Articles", marker_color="#0f3460", opacity=0.7,
        ))
        fig.add_trace(go.Scatter(
            x=df_hourly["hour"], y=df_hourly["avg_sentiment"],
            name="Avg Sentiment", yaxis="y2",
            line=dict(color="#e94560", width=2),
        ))
        fig.update_layout(
            template="plotly_dark",
            yaxis2=dict(overlaying="y", side="right", title="Sentiment (-1 to 1)"),
            legend=dict(x=0, y=1),
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hourly data yet.")

with chart_col2:
    st.subheader("🥧 Sentiment Distribution")
    if not df.empty and "sentiment_label" in df.columns:
        counts = df["sentiment_label"].value_counts().reset_index()
        counts.columns = ["label", "count"]
        colors = {"POSITIVE": "#00ff88", "NEGATIVE": "#ff4444", "NEUTRAL": "#888888"}
        fig2 = px.pie(
            counts, values="count", names="label",
            color="label", color_discrete_map=colors,
            template="plotly_dark", hole=0.45,
        )
        fig2.update_layout(height=350)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No sentiment data yet.")


# ── Charts Row 2 ──────────────────────────────────────────────────────────────
chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    st.subheader("🏦 Articles by Source")
    if not df_sources.empty:
        fig3 = px.bar(
            df_sources, x="articles", y="source", orientation="h",
            color="avg_sentiment", color_continuous_scale="RdYlGn",
            template="plotly_dark",
        )
        fig3.update_layout(height=350, coloraxis_showscale=False)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No source data yet.")

with chart_col4:
    st.subheader("🔥 Trending Topics")
    if not df_trend.empty:
        df_t = df_trend.head(10)
        fig4 = px.bar(
            df_t, x="mention_count", y="topic", orientation="h",
            color="avg_sentiment", color_continuous_scale="RdYlGn",
            template="plotly_dark",
        )
        fig4.update_layout(height=350, coloraxis_showscale=False)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No trending data yet.")


# ── Trending Stocks & Sectors ─────────────────────────────────────────────────
st.markdown("---")
ts_col1, ts_col2 = st.columns(2)

def _badge(label: str, val: str) -> str:
    cls = f"badge-{val.lower()}" if val.lower() in ("positive","negative","bullish","bearish","neutral") else "badge-neutral"
    return f'<span class="badge {cls}">{val}</span>'

with ts_col1:
    st.subheader("📌 Trending Stocks")
    if not df_trend.empty:
        stocks = df_trend[df_trend["topic_type"] == "STOCK"].head(8)
        if not stocks.empty:
            for _, row in stocks.iterrows():
                col = "🟢" if row.get("avg_sentiment", 0) > 0.1 else ("🔴" if row.get("avg_sentiment", 0) < -0.1 else "⚪")
                st.markdown(f"{col} **{row['topic']}** — {int(row['mention_count'])} mentions")
        else:
            st.info("No stock data yet.")
    else:
        st.info("No trending data.")

with ts_col2:
    st.subheader("🏭 Trending Sectors")
    if not df_trend.empty:
        sectors = df_trend[df_trend["topic_type"] == "SECTOR"].head(8)
        if not sectors.empty:
            for _, row in sectors.iterrows():
                col = "🟢" if row.get("avg_sentiment", 0) > 0.1 else ("🔴" if row.get("avg_sentiment", 0) < -0.1 else "⚪")
                st.markdown(f"{col} **{row['topic']}** — {int(row['mention_count'])} mentions")
        else:
            st.info("No sector data yet.")
    else:
        st.info("No trending data.")


# ── Live News Feed ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader(f"📡 Live News Feed ({len(df)} articles)")

if df.empty:
    st.warning("No articles found. Run the Airflow ETL DAG to populate data.")
else:
    # Sort by publish date
    if "publish_date" in df.columns:
        df = df.sort_values("publish_date", ascending=False, na_position="last")

    items_per_page = 20
    total_pages = max(1, (len(df) - 1) // items_per_page + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1) - 1
    page_df = df.iloc[page * items_per_page: (page + 1) * items_per_page]

    for _, row in page_df.iterrows():
        sentiment = row.get("sentiment_label", "NEUTRAL") or "NEUTRAL"
        direction = row.get("market_direction", "NEUTRAL") or "NEUTRAL"
        impact    = row.get("market_impact_score", 0) or 0
        score     = row.get("sentiment_score", 0) or 0

        card_class = "positive" if sentiment == "POSITIVE" else ("negative" if sentiment == "NEGATIVE" else "news-card")
        pub = row.get("publish_date")
        pub_str = pub.strftime("%b %d %H:%M") if pd.notnull(pub) else "Unknown"

        headline  = row.get("headline", "")
        url       = row.get("source_url", "#")
        source    = row.get("source", "")
        summary   = row.get("summary", "") or ""
        tickers   = row.get("mentioned_tickers", []) or []
        sectors   = row.get("mentioned_sectors", []) or []

        ticker_html = " ".join(f'<code>{t}</code>' for t in (tickers[:5] if isinstance(tickers, list) else []))

        st.markdown(f"""
<div class="news-card {card_class}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span style="color:#888;font-size:12px">{source} · {pub_str}</span>
    <div>
      <span class="badge badge-{sentiment.lower()}">{sentiment}</span>&nbsp;
      <span class="badge badge-{direction.lower()}">{direction}</span>&nbsp;
      <span class="badge badge-neutral">⚡ {impact:.0f}</span>
    </div>
  </div>
  <h4 style="margin:8px 0"><a href="{url}" target="_blank" style="color:#e0e0e0;text-decoration:none">{headline}</a></h4>
  <p style="color:#aaa;font-size:13px;margin:4px 0">{summary[:200]}{"..." if len(summary) > 200 else ""}</p>
  <div style="margin-top:6px">{ticker_html}</div>
</div>
""", unsafe_allow_html=True)

    st.caption(f"Page {page+1} of {total_pages}")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#555'>Finance AI Monitor · Built with Streamlit, "
    "Scrapy, Airflow, PostgreSQL, OpenAI · UCP BSDS Project</p>",
    unsafe_allow_html=True,
)
