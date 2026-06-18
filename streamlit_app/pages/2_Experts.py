"""
streamlit_app/pages/2_Experts.py — Finance Expert Management
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
import pandas as pd
from database.db import init_pool, get_cursor

st.set_page_config(page_title="Expert Management", page_icon="👥", layout="wide")
init_pool()

st.title("👥 Finance Expert Management")
st.markdown("Manage expert profiles and their alert preferences.")

# ── Load experts ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_experts():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM finance_experts ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

@st.cache_data(ttl=30)
def load_prefs():
    with get_cursor() as cur:
        cur.execute("""
            SELECT ap.*, fe.full_name, fe.email
            FROM alert_preferences ap
            JOIN finance_experts fe ON ap.expert_id = fe.id
        """)
        return [dict(r) for r in cur.fetchall()]


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Expert List", "➕ Add Expert", "🔔 Alert Preferences"])

with tab1:
    experts = load_experts()
    if experts:
        df = pd.DataFrame(experts)
        df["status"] = df["is_active"].apply(lambda x: "✅ Active" if x else "❌ Inactive")
        st.dataframe(
            df[["full_name", "email", "organization", "role", "status", "created_at"]],
            use_container_width=True,
        )
    else:
        st.info("No experts registered yet.")

    # Deactivate
    with st.expander("⚙️ Manage Expert Status"):
        if experts:
            names = [f"{e['full_name']} ({e['email']})" for e in experts]
            sel = st.selectbox("Select expert", names)
            idx = names.index(sel)
            expert = experts[idx]
            col1, col2 = st.columns(2)
            if col1.button("✅ Activate"):
                with get_cursor() as cur:
                    cur.execute("UPDATE finance_experts SET is_active=TRUE  WHERE id=%s", (expert["id"],))
                st.success("Expert activated.")
                st.cache_data.clear()
                st.rerun()
            if col2.button("❌ Deactivate"):
                with get_cursor() as cur:
                    cur.execute("UPDATE finance_experts SET is_active=FALSE WHERE id=%s", (expert["id"],))
                st.success("Expert deactivated.")
                st.cache_data.clear()
                st.rerun()

with tab2:
    st.subheader("Add New Expert")
    with st.form("add_expert_form"):
        full_name    = st.text_input("Full Name *")
        email        = st.text_input("Email *")
        organization = st.text_input("Organization")
        role         = st.text_input("Role")
        submitted    = st.form_submit_button("Add Expert")

    if submitted:
        if not full_name or not email:
            st.error("Full Name and Email are required.")
        else:
            try:
                with get_cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO finance_experts (full_name, email, organization, role)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (email) DO NOTHING RETURNING id
                        """,
                        (full_name, email, organization, role),
                    )
                    row = cur.fetchone()
                if row:
                    # Default preferences
                    with get_cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO alert_preferences
                                (expert_id, alert_type, send_breaking_news,
                                 send_daily_summary, send_weekly_report)
                            VALUES (%s, 'ALL', TRUE, TRUE, TRUE)
                            ON CONFLICT DO NOTHING
                            """,
                            (str(row["id"]),),
                        )
                    st.success(f"Expert '{full_name}' added successfully!")
                    st.cache_data.clear()
                else:
                    st.warning("Email already exists.")
            except Exception as e:
                st.error(f"Error: {e}")

with tab3:
    st.subheader("Alert Preferences")
    prefs = load_prefs()
    if prefs:
        for p in prefs:
            with st.expander(f"🔔 {p['full_name']} ({p['email']})"):
                cols = st.columns(3)
                cols[0].metric("Breaking News", "✅" if p.get("send_breaking_news") else "❌")
                cols[1].metric("Daily Summary", "✅" if p.get("send_daily_summary") else "❌")
                cols[2].metric("Weekly Report", "✅" if p.get("send_weekly_report") else "❌")

                st.write(f"**Sentiment Threshold:** {p.get('sentiment_threshold', 0.7)}")
                st.write(f"**Impact Threshold:** {p.get('impact_threshold', 70.0)}")

                # Edit
                with st.form(f"pref_form_{p['id']}"):
                    breaking  = st.checkbox("Breaking News Alerts", value=bool(p.get("send_breaking_news")))
                    daily     = st.checkbox("Daily Summary",         value=bool(p.get("send_daily_summary")))
                    weekly    = st.checkbox("Weekly Report",         value=bool(p.get("send_weekly_report")))
                    sent_thr  = st.slider("Sentiment Threshold", 0.0, 1.0,
                                          float(p.get("sentiment_threshold", 0.7)), step=0.05)
                    imp_thr   = st.slider("Impact Threshold",    0.0, 100.0,
                                          float(p.get("impact_threshold", 70.0)),   step=5.0)
                    if st.form_submit_button("💾 Save Preferences"):
                        with get_cursor() as cur:
                            cur.execute(
                                """
                                UPDATE alert_preferences
                                SET send_breaking_news=%s, send_daily_summary=%s,
                                    send_weekly_report=%s, sentiment_threshold=%s,
                                    impact_threshold=%s
                                WHERE id=%s
                                """,
                                (breaking, daily, weekly, sent_thr, imp_thr, p["id"]),
                            )
                        st.success("Preferences saved!")
                        st.cache_data.clear()
    else:
        st.info("No alert preferences configured.")
