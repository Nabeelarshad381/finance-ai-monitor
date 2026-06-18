"""
scripts/run_scrapers.py
Manual script to run all scrapers outside of Airflow.
Usage:
    python scripts/run_scrapers.py                    # run all
    python scripts/run_scrapers.py --spider reuters   # run one spider
    python scripts/run_scrapers.py --selenium         # run only Selenium scrapers
    python scripts/run_scrapers.py --all              # run everything
"""

import argparse
import logging
import subprocess
import sys
import os
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"/tmp/scrapers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
logger = logging.getLogger("run_scrapers")

SCRAPY_SPIDERS = [
    "reuters",
    "yahoo_finance",
    "cnbc",
    "marketwatch",
    "investing_com",
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_scrapy_spider(spider_name: str) -> bool:
    """Run a single Scrapy spider. Returns True on success."""
    logger.info("▶ Starting spider: %s", spider_name)
    start = time.time()

    cmd = ["scrapy", "crawl", spider_name]
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
        )
        elapsed = round(time.time() - start, 1)
        if result.returncode == 0:
            logger.info("✅ Spider '%s' finished in %ss", spider_name, elapsed)
            return True
        else:
            logger.warning(
                "⚠️  Spider '%s' exited with code %d in %ss\nSTDERR: %s",
                spider_name, result.returncode, elapsed,
                result.stderr[-1000:] if result.stderr else "(none)",
            )
            return False
    except subprocess.TimeoutExpired:
        logger.error("⏰ Spider '%s' timed out after 600s", spider_name)
        return False
    except Exception as exc:
        logger.error("💥 Spider '%s' raised: %s", spider_name, exc)
        return False


def run_selenium_scrapers() -> bool:
    """Run Selenium-based scrapers (Bloomberg)."""
    logger.info("▶ Starting Selenium scrapers...")
    try:
        from database.db import init_pool
        init_pool()
        from scrapers.selenium.dynamic_scraper import run_selenium_scrapers as _run
        results = _run()
        for src, count in results.items():
            logger.info("  %s: %d new articles", src, count)
        return True
    except Exception as exc:
        logger.error("💥 Selenium scraper failed: %s", exc)
        return False


def run_ai_analysis(limit: int = 200) -> int:
    """Run AI analysis on unprocessed articles."""
    logger.info("▶ Running AI analysis (limit=%d)...", limit)
    try:
        from database.db import init_pool, get_unprocessed_articles, insert_analysis, mark_article_processed
        from ai_engine.analyzer import batch_analyse
        init_pool()

        articles = get_unprocessed_articles(limit=limit)
        logger.info("  Found %d unprocessed articles", len(articles))
        if not articles:
            return 0

        results = batch_analyse(articles, delay=0.5)
        saved = 0
        for res in results:
            try:
                insert_analysis(res)
                mark_article_processed(res["article_id"])
                saved += 1
            except Exception as e:
                logger.warning("  Failed to save analysis: %s", e)

        logger.info("✅ AI analysis saved %d records", saved)
        return saved
    except Exception as exc:
        logger.error("💥 AI analysis failed: %s", exc)
        return 0


def run_trending_topics():
    """Detect and store trending topics."""
    logger.info("▶ Detecting trending topics...")
    try:
        from datetime import timezone, timedelta
        from database.db import init_pool, get_cursor
        from ai_engine.analyzer import detect_trending_topics
        init_pool()

        with get_cursor() as cur:
            cur.execute("""
                SELECT key_topics, mentioned_tickers, mentioned_sectors,
                       sentiment_score, market_direction
                FROM article_analysis aa
                JOIN news_articles na ON aa.article_id = na.id
                WHERE na.scraped_at >= NOW() - INTERVAL '6 hours'
            """)
            rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            logger.info("  No recent analyses for trending topics")
            return

        import datetime as dt
        trends = detect_trending_topics(rows)
        now = dt.datetime.now(dt.timezone.utc)
        window_start = now - dt.timedelta(hours=6)

        with get_cursor() as cur:
            for t in trends:
                cur.execute("""
                    INSERT INTO trending_topics
                        (topic, topic_type, mention_count, avg_sentiment, window_start, window_end)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (t["topic"], t.get("topic_type","MACRO"),
                      t["mention_count"], t.get("avg_sentiment", 0),
                      window_start, now))

        logger.info("✅ Stored %d trending topics", len(trends))
    except Exception as exc:
        logger.error("💥 Trending topics failed: %s", exc)


def print_summary(results: dict):
    print("\n" + "="*55)
    print("  SCRAPER RUN SUMMARY")
    print("="*55)
    for name, success in results.items():
        status = "✅ OK" if success else "❌ FAIL"
        print(f"  {status}  {name}")
    ok    = sum(1 for v in results.values() if v)
    fail  = len(results) - ok
    print("="*55)
    print(f"  Total: {len(results)}  |  OK: {ok}  |  Failed: {fail}")
    print("="*55 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Finance Monitor — Manual Scraper Runner")
    parser.add_argument("--spider",   help="Run a single Scrapy spider by name")
    parser.add_argument("--selenium", action="store_true", help="Run only Selenium scrapers")
    parser.add_argument("--analyse",  action="store_true", help="Run AI analysis only")
    parser.add_argument("--trending", action="store_true", help="Run trending topics only")
    parser.add_argument("--all",      action="store_true", help="Run everything (default)")
    parser.add_argument("--limit",    type=int, default=200, help="AI analysis article limit")
    args = parser.parse_args()

    run_all = args.all or not any([args.spider, args.selenium, args.analyse, args.trending])

    results = {}
    start_time = time.time()

    if args.spider:
        results[args.spider] = run_scrapy_spider(args.spider)

    elif args.selenium:
        results["Selenium Scrapers"] = run_selenium_scrapers()

    elif args.analyse:
        count = run_ai_analysis(limit=args.limit)
        results["AI Analysis"] = count > 0 or True

    elif args.trending:
        run_trending_topics()
        results["Trending Topics"] = True

    else:  # run_all
        # 1. Scrapy spiders (sequential to be polite)
        for spider in SCRAPY_SPIDERS:
            results[f"scrapy:{spider}"] = run_scrapy_spider(spider)
            time.sleep(3)  # brief pause between spiders

        # 2. Selenium scrapers
        results["selenium:bloomberg"] = run_selenium_scrapers()

        # 3. AI analysis
        count = run_ai_analysis(limit=args.limit)
        results["ai_analysis"] = True

        # 4. Trending topics
        run_trending_topics()
        results["trending_topics"] = True

    total_time = round(time.time() - start_time, 1)
    print_summary(results)
    logger.info("Total run time: %ss", total_time)


if __name__ == "__main__":
    main()
