"""
streamlit_app/pages/1_News_Feed.py
Full-featured news feed with search, filters, and article detail view.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
import pandas as pd
from database.db import init_pool, get_cursor

st.set_page_config(page_title="News Feed", page_icon="📰", layout="wide")

@st.cache_resource
def _init():
    init_pool()
_init()

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .news-card {
    background: #1a1a2e; border-left: 4px solid #0f3460;
    border-radius: 8px; padding: 15px; margin-bottom: 12px;
  }
  .news-card.positive { border-left-color: #00ff88; }
  .news-card.negative { border-left-color: #ff4444; }
  .news-card.neutral  { border-left-color: #888888; }
  .badge {
    display: inline-block; padding: 2px 10px;
    border-radius: 20px; font-size: 11px; font-weight: bold; margin-right:4px;
  }
  .badge-POSITIVE,.badge-BULLISH { background:#003320; color:#00ff88; }
  .badge-NEGATIVE,.badge-BEARISH { background:#330000; color:#ff4444; }
  .badge-NEUTRAL  { background:#222;    color:#aaa; }
</style>
""", unsafe_allow_html=True)

st.title("📰 Finance News Feed")

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Filters")
    search      = st.text_input("🔍 Search headlines / text", "")
    hours       = st.selectbox("Time window", [3, 6, 12, 24, 48, 72, 168], index=3,
                               format_func=lambda h: f"Last {h}h" if h < 168 else "Last 7 days")
    sources     = st.multiselect("Source", ["Reuters","Yahoo Finance","CNBC",
                                            "Bloomberg","MarketWatch","Investing.com"])
    categories  = st.multiselect("Category", ["Finance","Markets","Economy","Technology",
                                              "Energy","Earnings","Investing","Policy"])
    sentiments  = st.multiselect("Sentiment",  ["POSITIVE","NEGATIVE","NEUTRAL"])
    directions  = st.multiselect("Direction",  ["BULLISH","BEARISH","NEUTRAL"])
    min_impact  = st.slider("Min Impact Score", 0, 100, 0, step=5)
    sort_by     = st.selectbox("Sort by", ["Publish Date","Impact Score","Sentiment Score"])
    per_page    = st.selectbox("Articles per page", [10, 20, 50], index=1)
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# ── Data loader ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=45)
def load_feed(hours: int, limit: int = 1000) -> pd.DataFrame:
    with get_cursor() as cur:
        cur.execute("""
            SELECT na.id, na.headline, na.full_text, na.author,
                   na.publish_date, na.source, na.source_url, na.category,
                   aa.sentiment_label, aa.sentiment_score,
                   aa.market_direction, aa.market_impact_score,
                   aa.summary, aa.mentioned_tickers, aa.mentioned_sectors,
                   aa.key_topics
            FROM news_articles na
            LEFT JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '%s hours'
            ORDER BY na.publish_date DESC NULLS LAST
            LIMIT %s
        """, (hours, limit))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["publish_date"]       = pd.to_datetime(df["publish_date"], utc=True, errors="coerce")
    df["sentiment_score"]    = pd.to_numeric(df["sentiment_score"],    errors="coerce").fillna(0)
    df["market_impact_score"]= pd.to_numeric(df["market_impact_score"],errors="coerce").fillna(0)
    return df

df = load_feed(hours)

# ── Apply filters ─────────────────────────────────────────────────────────────
if not df.empty:
    if search:
        mask = (df["headline"].str.contains(search, case=False, na=False) |
                df["full_text"].str.contains(search, case=False, na=False))
        df = df[mask]
    if sources:
        df = df[df["source"].isin(sources)]
    if categories:
        df = df[df["category"].isin(categories)]
    if sentiments:
        df = df[df["sentiment_label"].isin(sentiments)]
    if directions:
        df = df[df["market_direction"].isin(directions)]
    if min_impact > 0:
        df = df[df["market_impact_score"] >= min_impact]
    if sort_by == "Impact Score":
        df = df.sort_values("market_impact_score", ascending=False)
    elif sort_by == "Sentiment Score":
        df = df.sort_values("sentiment_score", ascending=False)

# ── Stats bar ─────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📰 Results",  len(df))
c2.metric("🟢 Positive", int((df["sentiment_label"]=="POSITIVE").sum()) if not df.empty else 0)
c3.metric("🔴 Negative", int((df["sentiment_label"]=="NEGATIVE").sum()) if not df.empty else 0)
c4.metric("🐂 Bullish",  int((df["market_direction"]=="BULLISH").sum())  if not df.empty else 0)
c5.metric("🐻 Bearish",  int((df["market_direction"]=="BEARISH").sum())  if not df.empty else 0)
st.markdown("---")

# ── Pagination ────────────────────────────────────────────────────────────────
if df.empty:
    st.info("No articles match your filters. Try adjusting the time window or filters.")
    st.stop()

total_pages = max(1, (len(df) - 1) // per_page + 1)
col_pg1, col_pg2 = st.columns([3, 1])
with col_pg2:
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1) - 1
with col_pg1:
    st.caption(f"Showing page {page+1} of {total_pages} ({len(df)} total articles)")

page_df = df.iloc[page * per_page : (page + 1) * per_page]

# ── Article cards ─────────────────────────────────────────────────────────────
for _, row in page_df.iterrows():
    sentiment = (row.get("sentiment_label") or "NEUTRAL").strip()
    direction = (row.get("market_direction") or "NEUTRAL").strip()
    impact    = float(row.get("market_impact_score") or 0)
    score_val = float(row.get("sentiment_score") or 0)
    headline  = row.get("headline") or "Untitled"
    url       = row.get("source_url") or "#"
    source    = row.get("source") or ""
    summary   = row.get("summary") or ""
    author    = row.get("author") or ""
    category  = row.get("category") or ""
    tickers   = row.get("mentioned_tickers") or []
    sectors   = row.get("mentioned_sectors") or []
    topics    = row.get("key_topics") or []
    pub       = row.get("publish_date")
    pub_str   = pub.strftime("%b %d, %Y %H:%M UTC") if pd.notnull(pub) else "Unknown date"

    card_class = sentiment.lower() if sentiment in ("POSITIVE","NEGATIVE") else "neutral"
    score_color = "#00ff88" if score_val > 0.1 else ("#ff4444" if score_val < -0.1 else "#888")

    tickers_html = " ".join(f'<code style="background:#0f3460;padding:1px 6px;border-radius:4px;font-size:11px">{t}</code>'
                            for t in (tickers[:6] if isinstance(tickers, list) else []))
    sectors_html = " ".join(f'<span style="background:#2c003e;color:#d7a3ff;padding:1px 7px;border-radius:4px;font-size:11px">{s}</span>'
                            for s in (sectors[:4] if isinstance(sectors, list) else []))

    st.markdown(f"""
<div class="news-card {card_class}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:6px">
    <div>
      <span style="color:#777;font-size:12px">🗓 {pub_str}</span>
      {"&nbsp;&nbsp;<span style='color:#aaa;font-size:12px'>✍ " + author + "</span>" if author else ""}
      {"&nbsp;&nbsp;<span style='color:#aaa;font-size:12px'>📂 " + category + "</span>" if category else ""}
    </div>
    <div>
      <span class="badge badge-{sentiment}">{sentiment}</span>
      <span class="badge badge-{direction}">{direction}</span>
      <span class="badge badge-NEUTRAL">⚡ {impact:.0f}/100</span>
      <span style="font-size:11px;color:{score_color}">score: {score_val:+.2f}</span>
    </div>
  </div>
  <h4 style="margin:10px 0 6px">
    <a href="{url}" target="_blank" style="color:#e8e8e8;text-decoration:none">
      {headline}
    </a>
    &nbsp;<span style="font-size:12px;color:#666">[{source}]</span>
  </h4>
  {f'<p style="color:#bbb;font-size:13px;margin:4px 0 8px">{summary[:250]}{"..." if len(summary) > 250 else ""}</p>' if summary else ""}
  <div style="margin-top:6px">{tickers_html}&nbsp;{sectors_html}</div>
</div>
""", unsafe_allow_html=True)

    # Expandable full text
    if row.get("full_text"):
        with st.expander("📄 Read full article text"):
            st.markdown(row["full_text"][:5000])
            if len(row["full_text"]) > 5000:
                st.caption("(truncated to 5000 chars — view full article at source)")

st.markdown("---")
st.caption(f"Page {page+1} / {total_pages}  •  Finance Monitor Platform")
