"""
database/db.py — PostgreSQL connection pool manager
Uses psycopg2 with a thread-safe connection pool.
"""

import os
import hashlib
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# ── Connection pool (created once at import time) ─────────────────────────────
_pool: Optional[pool.ThreadedConnectionPool] = None


def _get_dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'finance_monitor')} "
        f"user={os.getenv('POSTGRES_USER', 'finance_user')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'finance_pass')}"
    )


def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(minconn, maxconn, _get_dsn())
        logger.info("PostgreSQL connection pool initialised.")


@contextmanager
def get_conn():
    """Yield a connection from the pool; auto-return on exit."""
    global _pool
    if _pool is None:
        init_pool()
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor: bool = True):
    """Yield a cursor (RealDictCursor by default)."""
    cursor_factory = RealDictCursor if dict_cursor else None
    with get_conn() as conn:
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            yield cur


# ── Helpers ───────────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    """SHA-256 hash of a URL — used for deduplication."""
    return hashlib.sha256(url.encode()).hexdigest()


def article_exists(url: str) -> bool:
    h = url_hash(url)
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM news_articles WHERE url_hash = %s", (h,))
        return cur.fetchone() is not None


def insert_article(data: Dict[str, Any]) -> Optional[str]:
    """
    Insert a news article.  Returns the UUID on success, None if duplicate.
    data keys: headline, full_text, author, publish_date, source,
               source_url, category, url (used for hashing)
    """
    h = url_hash(data.get("source_url", data.get("url", "")))
    if article_exists(data.get("source_url", data.get("url", ""))):
        logger.debug("Duplicate article skipped: %s", data.get("headline", "")[:60])
        return None

    with get_cursor() as cur:
        db_data = {**data}
        pub_date = db_data.get("publish_date")
        if not pub_date or (isinstance(pub_date, str) and not pub_date.strip()):
            db_data["publish_date"] = None

        cur.execute(
            """
            INSERT INTO news_articles
                (headline, full_text, author, publish_date, source,
                 source_url, category, url_hash)
            VALUES
                (%(headline)s, %(full_text)s, %(author)s, %(publish_date)s,
                 %(source)s, %(source_url)s, %(category)s, %(url_hash)s)
            RETURNING id
            """,
            {**db_data, "url_hash": h, "source_url": db_data.get("source_url", db_data.get("url", ""))},
        )
        row = cur.fetchone()
        return str(row["id"]) if row else None


def get_unprocessed_articles(limit: int = 50) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, headline, full_text, source, category, publish_date
            FROM news_articles
            WHERE is_processed = FALSE
            ORDER BY scraped_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def mark_article_processed(article_id: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE news_articles SET is_processed = TRUE WHERE id = %s",
            (article_id,),
        )


def insert_analysis(data: Dict[str, Any]) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO article_analysis
                (article_id, sentiment_label, sentiment_score, market_direction,
                 market_impact_score, summary, key_topics, mentioned_tickers,
                 mentioned_sectors, confidence)
            VALUES
                (%(article_id)s, %(sentiment_label)s, %(sentiment_score)s,
                 %(market_direction)s, %(market_impact_score)s, %(summary)s,
                 %(key_topics)s, %(mentioned_tickers)s, %(mentioned_sectors)s,
                 %(confidence)s)
            ON CONFLICT (article_id) DO UPDATE SET
                sentiment_label     = EXCLUDED.sentiment_label,
                sentiment_score     = EXCLUDED.sentiment_score,
                market_direction    = EXCLUDED.market_direction,
                market_impact_score = EXCLUDED.market_impact_score,
                summary             = EXCLUDED.summary,
                key_topics          = EXCLUDED.key_topics,
                mentioned_tickers   = EXCLUDED.mentioned_tickers,
                mentioned_sectors   = EXCLUDED.mentioned_sectors,
                confidence          = EXCLUDED.confidence,
                analyzed_at         = NOW()
            """,
            data,
        )


def get_recent_articles_with_analysis(hours: int = 24, limit: int = 200) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                a.id, a.headline, a.author, a.publish_date, a.source,
                a.source_url, a.category,
                an.sentiment_label, an.sentiment_score, an.market_direction,
                an.market_impact_score, an.summary, an.key_topics,
                an.mentioned_tickers, an.mentioned_sectors
            FROM news_articles a
            LEFT JOIN article_analysis an ON a.id = an.article_id
            WHERE a.scraped_at >= NOW() - INTERVAL '%s hours'
            ORDER BY a.publish_date DESC NULLS LAST
            LIMIT %s
            """,
            (hours, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_trending_topics(hours: int = 6, limit: int = 20) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT topic, topic_type, mention_count, avg_sentiment
            FROM trending_topics
            WHERE window_end >= NOW() - INTERVAL '%s hours'
            ORDER BY mention_count DESC
            LIMIT %s
            """,
            (hours, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_active_experts() -> List[Dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.full_name, e.email, e.organization,
                   ap.alert_type, ap.sentiment_threshold, ap.impact_threshold,
                   ap.preferred_sources, ap.preferred_categories,
                   ap.preferred_tickers, ap.send_breaking_news,
                   ap.send_daily_summary, ap.send_weekly_report
            FROM finance_experts e
            JOIN alert_preferences ap ON e.id = ap.expert_id
            WHERE e.is_active = TRUE AND ap.is_active = TRUE
            """,
        )
        return [dict(r) for r in cur.fetchall()]


def log_alert(expert_id: str, alert_type: str, subject: str,
              body_preview: str, status: str = "SENT",
              error_message: str = None) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO alert_logs
                (expert_id, alert_type, subject, body_preview, status, error_message)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (expert_id, alert_type, subject, body_preview[:500], status, error_message),
        )
