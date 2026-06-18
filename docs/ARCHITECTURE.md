# Finance AI News & Trend Monitoring Platform — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Finance AI Monitor — Full Architecture             │
└─────────────────────────────────────────────────────────────────────┘

  DATA SOURCES          COLLECTION           PROCESSING
  ┌──────────┐         ┌──────────────┐     ┌──────────────────────┐
  │ Reuters  │────────▶│ Scrapy       │────▶│                      │
  │ Yahoo    │         │ Spiders      │     │  Apache Airflow       │
  │ CNBC     │────────▶│              │     │  ETL DAG (30-min)    │
  │ MarketWch│         └──────────────┘     │                      │
  │ Investng.│                              │  ┌────────────────┐  │
  │ Bloomberg│────────▶┌──────────────┐────▶│  │  Dedup Check   │  │
  └──────────┘         │ Selenium     │     │  │  (URL Hash)    │  │
                       │ Scraper      │     │  └────────────────┘  │
                       └──────────────┘     │          │           │
                                            │          ▼           │
                                            │  ┌────────────────┐  │
                                            │  │  PostgreSQL    │  │
                                            │  │  news_articles │  │
                                            │  └────────────────┘  │
                                            │          │           │
                                            │          ▼           │
                                            │  ┌────────────────┐  │
                                            │  │  OpenAI GPT    │  │
                                            │  │  AI Analyzer   │  │
                                            │  └────────────────┘  │
                                            │          │           │
                                            │          ▼           │
                                            │  ┌────────────────┐  │
                                            │  │  PostgreSQL    │  │
                                            │  │ article_analys │  │
                                            │  │ trending_topics│  │
                                            │  └────────────────┘  │
                                            └──────────────────────┘
                                                       │
                              ┌────────────────────────┼────────────────────────┐
                              ▼                        ▼                        ▼
                    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
                    │   Streamlit      │    │   n8n Workflows  │    │   Airflow        │
                    │   Dashboard      │    │                  │    │   Alert DAGs     │
                    │                  │    │  Breaking News   │    │                  │
                    │  Live News Feed  │    │  Daily Summary   │    │  Every 15 min    │
                    │  Sentiment Charts│    │  Weekly Report   │    │  08:00 UTC daily │
                    │  Trending Topics │    │  Threshold Alert │    │  09:00 Mon weekly│
                    │  Expert Mgmt     │    │                  │    │                  │
                    │  Analytics       │    └────────┬─────────┘    └──────────────────┘
                    │  Alert Logs      │             │
                    │  Scrape Monitor  │             ▼
                    └──────────────────┘   ┌──────────────────┐
                                           │   SMTP Email     │
                                           │   to Experts     │
                                           └──────────────────┘
```

---

## Component Details

### 1. Data Collection Layer

#### Scrapy Spiders (`scrapers/spiders/`)
| Spider | Source | Type | Delay |
|--------|--------|------|-------|
| `reuters` | Reuters Finance | Static HTML | 3s |
| `yahoo_finance` | Yahoo Finance | Static HTML | 2s |
| `cnbc` | CNBC | Static HTML | 3s |
| `marketwatch` | MarketWatch | Static HTML | 2s |
| `investing_com` | Investing.com | Static HTML | 5s |

All spiders share a common pipeline:
```
Spider → ValidationPipeline → DuplicationPipeline → PostgresPipeline
```

#### Selenium Scraper (`scrapers/selenium/dynamic_scraper.py`)
- Used for Bloomberg and any JS-rendered site
- Uses `undetected-chromedriver` to bypass bot detection
- Runs headless Chrome in Docker
- Falls back gracefully on timeout/error

#### Deduplication
- SHA-256 hash of the article URL stored as `url_hash` (CHAR 64)
- `UNIQUE` constraint on `url_hash` in PostgreSQL
- Checked before every insert — O(1) lookup via index

---

### 2. ETL Pipeline (Airflow)

```
┌─────────────────────────────────────────────────────┐
│  DAG: finance_etl_30min  (schedule: */30 * * * *)   │
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ reuters  │ │  yahoo   │ │   cnbc   │  [parallel] │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       │             │             │                  │
│  ┌──────────┐ ┌──────────┐                          │
│  │marketwtch│ │investing │  [parallel]               │
│  └────┬─────┘ └────┬─────┘                          │
│       │             │                                │
│  ┌──────────┐                                        │
│  │bloomberg │  [selenium, parallel]                  │
│  └────┬─────┘                                        │
│       └──────────────┬──────────────────────┐        │
│                      ▼                      │        │
│               ┌─────────────┐               │        │
│               │ ai_analysis │               │        │
│               └──────┬──────┘               │        │
│                      ▼                               │
│               ┌─────────────┐                        │
│               │  trending   │                        │
│               └──────┬──────┘                        │
│                      ▼                               │
│               ┌─────────────┐                        │
│               │   cleanup   │                        │
│               └─────────────┘                        │
└─────────────────────────────────────────────────────┘
```

**Alert DAGs:**
- `breaking_news_alert` — runs every 15 minutes, checks impact score ≥ 70
- `daily_summary_alert` — runs at 08:00 UTC daily
- `weekly_report_alert` — runs at 09:00 UTC every Monday

---

### 3. AI Analysis Engine (`ai_engine/analyzer.py`)

Each article is sent to `gpt-4o-mini` with a structured prompt.

**Output schema:**
```json
{
  "sentiment_label":     "POSITIVE | NEGATIVE | NEUTRAL",
  "sentiment_score":     -1.0 to 1.0,
  "market_direction":    "BULLISH | BEARISH | NEUTRAL",
  "market_impact_score": 0 to 100,
  "summary":             "2-3 sentence summary",
  "key_topics":          ["topic1", "topic2"],
  "mentioned_tickers":   ["AAPL", "TSLA"],
  "mentioned_sectors":   ["Technology", "Energy"],
  "confidence":          0.0 to 1.0
}
```

**Cost estimate:** ~$0.0002 per article with `gpt-4o-mini`
Processing 200 articles/hour ≈ $0.04/hour ≈ ~$1/day

---

### 4. Database Schema

```
news_articles (core)
    id (UUID PK)
    headline, full_text, author
    publish_date, source, source_url
    category, url_hash (UNIQUE)
    scraped_at, is_processed

article_analysis (1:1 with news_articles)
    id, article_id (FK)
    sentiment_label, sentiment_score
    market_direction, market_impact_score
    summary, key_topics[], mentioned_tickers[]
    mentioned_sectors[], confidence

trending_topics (time-windowed)
    topic, topic_type, mention_count
    avg_sentiment, window_start, window_end

finance_experts
    id, full_name, email, organization, role, is_active

alert_preferences (1:N with experts)
    expert_id, alert_type
    sentiment_threshold, impact_threshold
    preferred_sources[], preferred_categories[]
    send_breaking_news, send_daily_summary, send_weekly_report

alert_logs
    expert_id, alert_type, subject, body_preview
    sent_at, status, error_message

scrape_runs
    source, run_start, run_end
    articles_found, articles_new, status
```

---

### 5. n8n Alert Workflows

```
Airflow DAG
    │
    │  POST /webhook/breaking-news
    ▼
n8n: breaking_news_workflow.json
    ├── Webhook Trigger
    ├── Format Email (Code Node — builds HTML table)
    ├── Send Email (SMTP)
    └── Webhook Response

    │  POST /webhook/daily-summary
    ▼
n8n: daily_summary_workflow.json
    ├── Webhook Trigger
    ├── Format Email (stats + top stories + trends)
    ├── Send Email (SMTP)
    └── Webhook Response

    │  POST /webhook/weekly-report
    ▼
n8n: weekly_report_workflow.json
    ├── Webhook Trigger
    ├── Format Email (weekly stats by source + trends)
    ├── Send Email (SMTP)
    └── Webhook Response
```

---

### 6. Streamlit Dashboard Pages

| Page | Route | Description |
|------|-------|-------------|
| Home | `app.py` | KPI metrics, sentiment charts, trending tickers/sectors, live feed |
| News Feed | `pages/1_News_Feed.py` | Full feed with search, filters, pagination, article detail |
| Experts | `pages/2_Experts.py` | Add/manage experts and alert preferences |
| Analytics | `pages/3_Analytics.py` | Deep charts — impact distribution, time series, scatterplots |
| Alert Logs | `pages/4_Alert_Logs.py` | Email history, status tracking, CSV export |
| Scrape Monitor | `pages/5_Scrape_Monitor.py` | Pipeline health, run history, source reliability |

---

### 7. Docker Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `postgres` | postgres:15-alpine | 5432 | Primary database |
| `airflow-webserver` | apache/airflow:2.8.1 | 8080 | DAG UI + scheduling |
| `airflow-scheduler` | apache/airflow:2.8.1 | — | DAG execution |
| `streamlit` | custom (Dockerfile) | 8501 | Dashboard |
| `n8n` | n8nio/n8n:latest | 5678 | Alert workflows |
| `pgadmin` | dpage/pgadmin4 | 5050 | DB admin (dev profile) |

---

### 8. Data Flow — End to End

```
1. Airflow scheduler triggers finance_etl_30min DAG
2. Scrapy spiders + Selenium scraper run in parallel
3. Each article is:
   a. Extracted (headline, text, author, date, source, URL)
   b. Validated (must have headline, URL, source)
   c. Deduplicated (SHA-256 URL hash check against PostgreSQL)
   d. Stored in news_articles table
4. AI analysis task picks up unprocessed articles (limit 100/run)
5. Each article is sent to OpenAI GPT-4o-mini
6. Results stored in article_analysis table
7. Article marked as processed
8. Trending topics calculated from last 6h of analyses
9. Alert DAGs check thresholds every 15 minutes
10. n8n webhooks triggered → emails sent to experts
11. Streamlit dashboard queries DB every 60 seconds
```
