"""
airflow/dags/alert_dag.py
Alert DAG — triggers n8n webhooks for:
  • Breaking news (checked every 15 min via sub-DAG)
  • Daily summary (08:00 UTC)
  • Weekly report (Monday 09:00 UTC)
"""

import json
import logging
import os
import sys
from datetime import timedelta

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

sys.path.insert(0, "/opt/airflow/project")

logger = logging.getLogger(__name__)

N8N_BASE_URL       = os.getenv("N8N_WEBHOOK_BASE", "http://n8n:5678/webhook")
IMPACT_THRESHOLD   = float(os.getenv("BREAKING_IMPACT_THRESHOLD", "70"))
SENTIMENT_THRESHOLD= float(os.getenv("BREAKING_SENTIMENT_THRESHOLD", "0.7"))

default_args = {
    "owner":            "finance_monitor",
    "depends_on_past":  False,
    "email_on_failure": False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=2),
}


# ── BREAKING NEWS DAG (every 15 minutes) ─────────────────────────────────────

def check_breaking_news(**ctx):
    from database.db import init_pool, get_cursor, get_active_experts
    init_pool()

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT na.headline, na.source, na.source_url, na.publish_date,
                   aa.sentiment_label, aa.sentiment_score, aa.market_direction,
                   aa.market_impact_score, aa.summary, aa.mentioned_tickers
            FROM news_articles na
            JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '20 minutes'
              AND aa.market_impact_score >= %s
            ORDER BY aa.market_impact_score DESC
            LIMIT 5
            """,
            (IMPACT_THRESHOLD,),
        )
        breaking = [dict(r) for r in cur.fetchall()]

    if not breaking:
        logger.info("No breaking news this cycle.")
        return 0

    experts = get_active_experts()
    notified = 0
    for expert in experts:
        if not expert.get("send_breaking_news"):
            continue
        payload = {
            "expert_name":  expert["full_name"],
            "expert_email": expert["email"],
            "alert_type":   "BREAKING",
            "articles":     _serialise(breaking),
        }
        try:
            r = requests.post(
                f"{N8N_BASE_URL}/breaking-news",
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            notified += 1
        except Exception as exc:
            logger.warning("Failed to notify %s: %s", expert["email"], exc)

    logger.info("Breaking news sent to %d experts", notified)
    return notified


# ── DAILY SUMMARY DAG (08:00 UTC) ────────────────────────────────────────────

def send_daily_summary(**ctx):
    from database.db import init_pool, get_cursor, get_active_experts
    init_pool()

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)                                              AS total_articles,
                COUNT(*) FILTER(WHERE aa.sentiment_label='POSITIVE') AS positive_count,
                COUNT(*) FILTER(WHERE aa.sentiment_label='NEGATIVE') AS negative_count,
                COUNT(*) FILTER(WHERE aa.market_direction='BULLISH') AS bullish_count,
                COUNT(*) FILTER(WHERE aa.market_direction='BEARISH') AS bearish_count,
                AVG(aa.sentiment_score)                               AS avg_sentiment,
                AVG(aa.market_impact_score)                           AS avg_impact
            FROM news_articles na
            JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '24 hours'
            """
        )
        stats = dict(cur.fetchone())

        cur.execute(
            """
            SELECT na.headline, na.source, na.source_url,
                   aa.sentiment_label, aa.market_impact_score, aa.summary
            FROM news_articles na
            JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '24 hours'
            ORDER BY aa.market_impact_score DESC
            LIMIT 10
            """
        )
        top_stories = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT topic, topic_type, mention_count, avg_sentiment
            FROM trending_topics
            WHERE window_end >= NOW() - INTERVAL '24 hours'
            ORDER BY mention_count DESC
            LIMIT 10
            """
        )
        trending = [dict(r) for r in cur.fetchall()]

    experts = get_active_experts()
    sent = 0
    for expert in experts:
        if not expert.get("send_daily_summary"):
            continue
        payload = {
            "expert_name":  expert["full_name"],
            "expert_email": expert["email"],
            "alert_type":   "DAILY_SUMMARY",
            "stats":        _serialise(stats),
            "top_stories":  _serialise(top_stories),
            "trending":     _serialise(trending),
            "date":         ctx["ds"],
        }
        try:
            r = requests.post(
                f"{N8N_BASE_URL}/daily-summary",
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            sent += 1
        except Exception as exc:
            logger.warning("Daily summary failed for %s: %s", expert["email"], exc)

    logger.info("Daily summary sent to %d experts", sent)
    return sent


# ── WEEKLY REPORT DAG (Monday 09:00 UTC) ─────────────────────────────────────

def send_weekly_report(**ctx):
    from database.db import init_pool, get_cursor, get_active_experts
    init_pool()

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                na.source,
                COUNT(*)                                               AS articles,
                AVG(aa.sentiment_score)                                AS avg_sentiment,
                COUNT(*) FILTER(WHERE aa.market_direction='BULLISH')   AS bullish,
                COUNT(*) FILTER(WHERE aa.market_direction='BEARISH')   AS bearish
            FROM news_articles na
            JOIN article_analysis aa ON na.id = aa.article_id
            WHERE na.scraped_at >= NOW() - INTERVAL '7 days'
            GROUP BY na.source
            ORDER BY articles DESC
            """
        )
        by_source = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT topic, SUM(mention_count) AS total_mentions,
                   AVG(avg_sentiment) AS avg_sentiment
            FROM trending_topics
            WHERE window_end >= NOW() - INTERVAL '7 days'
            GROUP BY topic
            ORDER BY total_mentions DESC
            LIMIT 15
            """
        )
        weekly_trends = [dict(r) for r in cur.fetchall()]

    experts = get_active_experts()
    sent = 0
    for expert in experts:
        if not expert.get("send_weekly_report"):
            continue
        payload = {
            "expert_name":   expert["full_name"],
            "expert_email":  expert["email"],
            "alert_type":    "WEEKLY_REPORT",
            "by_source":     _serialise(by_source),
            "weekly_trends": _serialise(weekly_trends),
            "week_ending":   ctx["ds"],
        }
        try:
            r = requests.post(
                f"{N8N_BASE_URL}/weekly-report",
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            sent += 1
        except Exception as exc:
            logger.warning("Weekly report failed for %s: %s", expert["email"], exc)

    logger.info("Weekly report sent to %d experts", sent)
    return sent


def _serialise(obj):
    """Make Python objects JSON-safe (handles Decimal, date, etc.)."""
    import decimal
    from datetime import date, datetime

    def default(o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return str(o)

    return json.loads(json.dumps(obj, default=default))


# ── Breaking news DAG ─────────────────────────────────────────────────────────
breaking_dag = DAG(
    dag_id            = "breaking_news_alert",
    description       = "Check for breaking finance news every 15 minutes",
    schedule_interval = "*/15 * * * *",
    start_date        = days_ago(1),
    catchup           = False,
    max_active_runs   = 1,
    default_args      = default_args,
    tags              = ["finance", "alerts"],
)
PythonOperator(task_id="check_breaking_news",
               python_callable=check_breaking_news,
               dag=breaking_dag)

# ── Daily summary DAG ─────────────────────────────────────────────────────────
daily_dag = DAG(
    dag_id            = "daily_summary_alert",
    description       = "Send daily finance summary at 08:00 UTC",
    schedule_interval = "0 8 * * *",
    start_date        = days_ago(1),
    catchup           = False,
    max_active_runs   = 1,
    default_args      = default_args,
    tags              = ["finance", "alerts"],
)
PythonOperator(task_id="send_daily_summary",
               python_callable=send_daily_summary,
               dag=daily_dag)

# ── Weekly report DAG ─────────────────────────────────────────────────────────
weekly_dag = DAG(
    dag_id            = "weekly_report_alert",
    description       = "Send weekly finance report every Monday at 09:00 UTC",
    schedule_interval = "0 9 * * 1",
    start_date        = days_ago(1),
    catchup           = False,
    max_active_runs   = 1,
    default_args      = default_args,
    tags              = ["finance", "alerts"],
)
PythonOperator(task_id="send_weekly_report",
               python_callable=send_weekly_report,
               dag=weekly_dag)
