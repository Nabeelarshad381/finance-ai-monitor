"""
airflow/dags/finance_etl_dag.py
Main ETL DAG — runs every 30 minutes:
  1. Scrapy spiders (Reuters, Yahoo Finance, CNBC, MarketWatch, Investing.com)
  2. Selenium scraper (Bloomberg)
  3. AI analysis (sentiment, impact scoring, topic detection)
  4. Trending topics calculation
  5. Cleanup (mark processed, update scrape run logs)
"""

import logging
import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# Add project root to path
sys.path.insert(0, "/opt/airflow/project")

logger = logging.getLogger(__name__)

# ── DAG defaults ──────────────────────────────────────────────────────────────
default_args = {
    "owner":            "finance_monitor",
    "depends_on_past":  False,
    "email_on_failure": False,
    "email_on_retry":   False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=3),
}

dag = DAG(
    dag_id            = "finance_etl_30min",
    description       = "Finance news ETL pipeline — runs every 30 minutes",
    schedule_interval = "*/30 * * * *",
    start_date        = days_ago(1),
    catchup           = False,
    max_active_runs   = 1,
    default_args      = default_args,
    tags              = ["finance", "etl", "scraping"],
)


# ── Task functions ─────────────────────────────────────────────────────────────

def _run_scrapy_spider(spider_name: str) -> int:
    """Run a Scrapy spider as a subprocess."""
    from database.db import init_pool
    init_pool()

    cmd = [
        "scrapy", "crawl", spider_name,
        "-s", "PROJECT_DIR=/opt/airflow/project",
        "--logfile", f"/tmp/scrapy_{spider_name}.log",
    ]
    result = subprocess.run(
        cmd,
        cwd="/opt/airflow/project",
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max per spider
    )
    if result.returncode != 0:
        logger.warning("Spider %s exited with code %d:\n%s",
                       spider_name, result.returncode, result.stderr[-2000:])
    logger.info("Spider %s completed.", spider_name)
    return result.returncode


def task_scrape_reuters(**ctx):
    return _run_scrapy_spider("reuters")


def task_scrape_yahoo(**ctx):
    return _run_scrapy_spider("yahoo_finance")


def task_scrape_cnbc(**ctx):
    return _run_scrapy_spider("cnbc")


def task_scrape_marketwatch(**ctx):
    return _run_scrapy_spider("marketwatch")


def task_scrape_investing(**ctx):
    return _run_scrapy_spider("investing_com")


def task_scrape_bloomberg(**ctx):
    """Run Selenium-based Bloomberg scraper."""
    from database.db import init_pool
    init_pool()
    from scrapers.selenium.dynamic_scraper import BloombergScraper
    with BloombergScraper(headless=True) as s:
        count = s.run_and_save()
    logger.info("Bloomberg Selenium scraper saved %d articles", count)
    return count


def task_ai_analysis(**ctx):
    """Run AI analysis on unprocessed articles."""
    from database.db import (
        init_pool, get_unprocessed_articles,
        insert_analysis, mark_article_processed,
    )
    from ai_engine.analyzer import batch_analyse

    init_pool()
    articles = get_unprocessed_articles(limit=100)
    logger.info("Found %d unprocessed articles", len(articles))
    if not articles:
        return 0

    results = batch_analyse(articles, delay=0.3)
    saved = 0
    for res in results:
        try:
            insert_analysis(res)
            mark_article_processed(res["article_id"])
            saved += 1
        except Exception as exc:
            logger.warning("Failed to save analysis for %s: %s",
                           res.get("article_id"), exc)

    logger.info("Saved %d analysis records", saved)
    return saved


def task_trending_topics(**ctx):
    """Detect and store trending topics from recent analyses."""
    from datetime import datetime, timezone, timedelta
    from database.db import init_pool, get_cursor
    from ai_engine.analyzer import detect_trending_topics

    init_pool()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT aa.key_topics, aa.mentioned_tickers, aa.mentioned_sectors,
                   aa.sentiment_score, aa.market_direction
            FROM article_analysis aa
            JOIN news_articles na ON aa.article_id = na.id
            WHERE na.scraped_at >= NOW() - INTERVAL '6 hours'
            """,
        )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        logger.info("No recent analyses for trending topics")
        return 0

    trends = detect_trending_topics(rows)
    now    = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=6)

    with get_cursor() as cur:
        for t in trends:
            cur.execute(
                """
                INSERT INTO trending_topics
                    (topic, topic_type, mention_count, avg_sentiment,
                     window_start, window_end)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    t["topic"], t.get("topic_type", "MACRO"),
                    t["mention_count"], t.get("avg_sentiment", 0),
                    window_start, now,
                ),
            )

    logger.info("Stored %d trending topics", len(trends))
    return len(trends)


def task_cleanup(**ctx):
    """Remove very old scrape run logs and temp files."""
    from database.db import init_pool, get_cursor
    init_pool()
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM scrape_runs WHERE run_start < NOW() - INTERVAL '7 days'"
        )
        cur.execute(
            "DELETE FROM trending_topics WHERE calculated_at < NOW() - INTERVAL '48 hours'"
        )
    logger.info("Cleanup completed")


# ── Task definitions ──────────────────────────────────────────────────────────

t_reuters     = PythonOperator(task_id="scrape_reuters",     python_callable=task_scrape_reuters,     dag=dag)
t_yahoo       = PythonOperator(task_id="scrape_yahoo",       python_callable=task_scrape_yahoo,       dag=dag)
t_cnbc        = PythonOperator(task_id="scrape_cnbc",        python_callable=task_scrape_cnbc,        dag=dag)
t_marketwatch = PythonOperator(task_id="scrape_marketwatch", python_callable=task_scrape_marketwatch, dag=dag)
t_investing   = PythonOperator(task_id="scrape_investing",   python_callable=task_scrape_investing,   dag=dag)
t_bloomberg   = PythonOperator(task_id="scrape_bloomberg",   python_callable=task_scrape_bloomberg,   dag=dag)
t_analysis    = PythonOperator(task_id="ai_analysis",        python_callable=task_ai_analysis,        dag=dag)
t_trending    = PythonOperator(task_id="trending_topics",    python_callable=task_trending_topics,    dag=dag)
t_cleanup     = PythonOperator(task_id="cleanup",            python_callable=task_cleanup,            dag=dag)

# ── Task dependencies ──────────────────────────────────────────────────────────
# All scrapers run in parallel, then AI analysis, then trending, then cleanup
[t_reuters, t_yahoo, t_cnbc, t_marketwatch, t_investing, t_bloomberg] >> t_analysis
t_analysis >> t_trending >> t_cleanup
