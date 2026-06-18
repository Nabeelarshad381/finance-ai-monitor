"""
streamlit_app/pages/4_Alert_Logs.py
View alert history — sent emails, statuses, and previews.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
import pandas as pd
from database.db import init_pool, get_cursor

st.set_page_config(page_title="Alert Logs", page_icon="🔔", layout="wide")

@st.cache_resource
def _init():
    init_pool()
_init()

st.title("🔔 Alert Logs")
st.markdown("History of all automated alerts sent to finance experts.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    days     = st.selectbox("Time window", [1, 3, 7, 14, 30], index=2,
                            format_func=lambda d: f"Last {d} day{'s' if d>1 else ''}")
    statuses = st.multiselect("Status", ["SENT","FAILED","PENDING"], default=["SENT","FAILED"])
    types    = st.multiselect("Alert Type", ["BREAKING","DAILY_SUMMARY","WEEKLY_REPORT"])
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# ── Data ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_logs(days: int) -> pd.DataFrame:
    with get_cursor() as cur:
        cur.execute("""
            SELECT al.id, fe.full_name, fe.email, al.alert_type,
                   al.subject, al.body_preview, al.sent_at,
                   al.status, al.error_message
            FROM alert_logs al
            LEFT JOIN finance_experts fe ON al.expert_id = fe.id
            WHERE al.sent_at >= NOW() - INTERVAL '%s days'
            ORDER BY al.sent_at DESC
            LIMIT 500
        """, (days,))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["sent_at"] = pd.to_datetime(df["sent_at"], utc=True, errors="coerce")
    return df

df = load_logs(days)

# ── Apply filters ─────────────────────────────────────────────────────────────
if not df.empty:
    if statuses:
        df = df[df["status"].isin(statuses)]
    if types:
        df = df[df["alert_type"].isin(types)]

# ── KPI row ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("📨 Total Alerts", len(df))
c2.metric("✅ Sent",   int((df["status"]=="SENT").sum())   if not df.empty else 0)
c3.metric("❌ Failed", int((df["status"]=="FAILED").sum()) if not df.empty else 0)
c4.metric("⏳ Pending",int((df["status"]=="PENDING").sum())if not df.empty else 0)
st.markdown("---")

if df.empty:
    st.info("No alert logs found for the selected filters.")
    st.stop()

# ── Summary charts ────────────────────────────────────────────────────────────
import plotly.express as px

col1, col2 = st.columns(2)
with col1:
    st.subheader("Alerts by Type")
    type_counts = df["alert_type"].value_counts().reset_index()
    type_counts.columns = ["type","count"]
    fig = px.bar(type_counts, x="type", y="count", template="plotly_dark",
                 color="type", color_discrete_sequence=["#0f3460","#e94560","#533483","#00b4d8"])
    fig.update_layout(height=280, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Alert Status Breakdown")
    status_counts = df["status"].value_counts().reset_index()
    status_counts.columns = ["status","count"]
    color_map = {"SENT":"#00ff88","FAILED":"#ff4444","PENDING":"#f39c12"}
    fig2 = px.pie(status_counts, values="count", names="status",
                  color="status", color_discrete_map=color_map,
                  template="plotly_dark", hole=0.4)
    fig2.update_layout(height=280)
    st.plotly_chart(fig2, use_container_width=True)

# ── Logs table ────────────────────────────────────────────────────────────────
st.subheader("📋 Alert Log Entries")

# Colour-code the status column
def _colour_status(val):
    if val == "SENT":
        return "color: #00ff88"
    elif val == "FAILED":
        return "color: #ff4444"
    return "color: #f39c12"

display_cols = ["sent_at","full_name","email","alert_type","status","subject","body_preview"]
display_df   = df[[c for c in display_cols if c in df.columns]].copy()
display_df["sent_at"] = display_df["sent_at"].dt.strftime("%Y-%m-%d %H:%M UTC")

st.dataframe(
    display_df.style.applymap(_colour_status, subset=["status"]),
    use_container_width=True,
    height=450,
)

# ── Failed alerts detail ──────────────────────────────────────────────────────
failed = df[df["status"] == "FAILED"]
if not failed.empty:
    st.markdown("---")
    st.subheader(f"⚠️ Failed Alerts ({len(failed)})")
    for _, row in failed.iterrows():
        with st.expander(f"❌ {row.get('full_name','Unknown')} — {row.get('alert_type','')} — {row.get('sent_at','')}"):
            st.markdown(f"**Email:** {row.get('email','')}")
            st.markdown(f"**Subject:** {row.get('subject','')}")
            if row.get("error_message"):
                st.error(f"Error: {row['error_message']}")

# ── CSV export ────────────────────────────────────────────────────────────────
st.markdown("---")
csv = display_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Export Logs as CSV", csv, "alert_logs.csv", "text/csv")
