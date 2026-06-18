# 📈 Finance AI News & Trend Monitoring Platform

> A production-ready, AI-powered platform that automatically collects, analyses, and visualises financial news from 6 major sources — with real-time sentiment analysis, bullish/bearish detection, automated expert alerts, and an interactive Streamlit dashboard.

**Built for:** University of Central Punjab — BSDS Final Year / Semester Project  
**Tools:** Scrapy · Selenium · BeautifulSoup · Apache Airflow · OpenAI · PostgreSQL · n8n · Streamlit · Docker

---

## 🏗️ Architecture

```
Reuters / Yahoo / CNBC / Bloomberg / MarketWatch / Investing.com
        ↓ Scrapy Spiders + Selenium
   Apache Airflow ETL (every 30 min)
        ↓ Dedup → PostgreSQL
   OpenAI GPT-4o-mini Analysis
        ↓ Sentiment · Bullish/Bearish · Impact · Topics · Summary
   Trending Topics Calculation
        ↓
   n8n Alert Workflows → Expert Emails
        ↓
   Streamlit Dashboard (real-time)
```

Full architecture diagram → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## 📁 Project Structure

```
finance_monitor/
├── scrapers/
│   ├── spiders/
│   │   ├── reuters_spider.py       Scrapy spider — Reuters Finance
│   │   └── finance_spiders.py      Scrapy spiders — Yahoo/CNBC/MarketWatch/Investing
│   ├── selenium/
│   │   └── dynamic_scraper.py      Selenium scraper — Bloomberg + JS sites
│   ├── items.py                    Scrapy item definitions
│   ├── pipelines.py                Validation → Dedup → PostgreSQL pipeline
│   └── settings.py                 Scrapy configuration
├── airflow/
│   └── dags/
│       ├── finance_etl_dag.py      Main ETL DAG (every 30 min)
│       └── alert_dag.py            Alert DAGs (breaking/daily/weekly)
├── ai_engine/
│   └── analyzer.py                 OpenAI analysis engine
├── database/
│   ├── schema.sql                  Full PostgreSQL schema
│   └── db.py                       Connection pool + helper functions
├── n8n_workflows/
│   ├── breaking_news_workflow.json n8n breaking news alert
│   ├── daily_summary_workflow.json n8n daily summary email
│   └── weekly_report_workflow.json n8n weekly report email
├── streamlit_app/
│   ├── app.py                      Main dashboard (KPIs + charts + feed)
│   └── pages/
│       ├── 1_News_Feed.py          Full news feed with search & filters
│       ├── 2_Experts.py            Expert management & alert preferences
│       ├── 3_Analytics.py          Deep analytics & charts
│       ├── 4_Alert_Logs.py         Alert history & status
│       └── 5_Scrape_Monitor.py     Scraper pipeline health
├── scripts/
│   ├── init_db.sh                  Docker DB initialisation
│   ├── apply_schema.py             Manual schema apply
│   └── run_scrapers.py             Manual scraper runner
├── tests/
│   ├── test_analyzer.py            AI engine unit tests
│   ├── test_scrapers.py            Spider & pipeline tests
│   └── test_db.py                  DB helper tests
├── docs/
│   └── ARCHITECTURE.md             Full architecture docs
├── Dockerfile                      App container
├── docker-compose.yml              Full stack orchestration
├── requirements.txt                Python dependencies
├── scrapy.cfg                      Scrapy project config
├── .env.example                    Environment variable template
└── README.md                       This file
```

---

## ⚡ Quick Start (Docker — Recommended)

### Prerequisites
- Docker Desktop (or Docker Engine + Compose)
- OpenAI API key
- SMTP credentials (Gmail App Password recommended)

### 1. Clone & Configure

```bash
git clone https://github.com/your-repo/finance_monitor.git
cd finance_monitor

# Copy and fill in your credentials
cp .env.example .env
nano .env   # or code .env
```

**Minimum required in `.env`:**
```env
OPENAI_API_KEY=sk-your-key-here
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your@gmail.com
```

### 2. Launch All Services

```bash
docker-compose up --build -d
```

This starts:
- PostgreSQL (with auto-schema apply)
- Airflow Webserver + Scheduler
- Streamlit Dashboard
- n8n Workflow Engine

### 3. Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Streamlit Dashboard | http://localhost:8501 | — |
| Airflow UI | http://localhost:8080 | admin / admin123 |
| n8n Workflows | http://localhost:5678 | admin / admin123 |
| pgAdmin (dev only) | http://localhost:5050 | admin@financemonitor.io / admin123 |

> Start pgAdmin: `docker-compose --profile dev up -d pgadmin`

### 4. Import n8n Workflows

1. Open http://localhost:5678
2. Go to **Workflows → Import**
3. Import all 3 files from `n8n_workflows/`
4. Add SMTP credentials in **Credentials** menu
5. Activate all workflows

### 5. Enable Airflow DAGs

1. Open http://localhost:8080
2. Enable these DAGs:
   - `finance_etl_30min` (runs every 30 min)
   - `breaking_news_alert` (every 15 min)
   - `daily_summary_alert` (08:00 UTC)
   - `weekly_report_alert` (Monday 09:00 UTC)
3. Trigger `finance_etl_30min` manually for first run

---

## 🖥️ Local Development Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start PostgreSQL Only

```bash
docker-compose up -d postgres
```

### 4. Apply Database Schema

```bash
python scripts/apply_schema.py
```

### 5. Set Environment Variables

```bash
# Windows PowerShell
$env:POSTGRES_HOST="localhost"
$env:OPENAI_API_KEY="sk-your-key"

# Linux/Mac
export POSTGRES_HOST=localhost
export OPENAI_API_KEY=sk-your-key
```

### 6. Run Scrapers Manually

```bash
# Run all scrapers
python scripts/run_scrapers.py --all

# Run a single Scrapy spider
python scripts/run_scrapers.py --spider reuters

# Run only Selenium scrapers
python scripts/run_scrapers.py --selenium

# Run AI analysis only
python scripts/run_scrapers.py --analyse --limit 50
```

### 7. Run Streamlit Dashboard

```bash
streamlit run streamlit_app/app.py
```

---

## 🧪 Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_analyzer.py -v
pytest tests/test_scrapers.py -v
pytest tests/test_db.py -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html
```

**Test coverage areas:**
- `test_analyzer.py` — AI result validation, trending detection, edge cases
- `test_scrapers.py` — Item fields, pipeline validation/dedup, spider HTML parsing
- `test_db.py` — URL hashing, insert/query mocks, alert logging

---

## 📊 Dashboard Features

### Home Page
- 6 KPI metrics (total articles, sentiment breakdown, bullish/bearish counts, avg impact)
- Hourly article volume + sentiment trend chart
- Sentiment distribution pie chart
- Articles by source bar chart
- Trending topics bar chart
- Live news feed with article cards

### News Feed Page (`/1_News_Feed`)
- Full-text search across headlines and article content
- Filters: source, category, sentiment, direction, impact score
- Sortable by: publish date, impact score, sentiment score
- Paginated results (10/20/50 per page)
- Colour-coded article cards with badges
- Expandable full article text

### Experts Page (`/2_Experts`)
- Add/remove/activate/deactivate experts
- Configure per-expert alert preferences
- Set sentiment and impact thresholds
- Toggle breaking news / daily / weekly alerts

### Analytics Page (`/3_Analytics`)
- Impact score distribution histogram
- Sentiment by source bar chart
- Daily sentiment trend line chart
- Articles by category pie chart
- Bullish vs bearish by source
- Sentiment vs impact scatter plot

### Alert Logs Page (`/4_Alert_Logs`)
- Full alert history with status (SENT/FAILED/PENDING)
- Filter by time window, status, alert type
- Charts: alerts by type, status breakdown
- Failed alert error details
- CSV export

### Scrape Monitor Page (`/5_Scrape_Monitor`)
- Per-source article counts (total, last 24h, last 1h)
- Hourly stacked bar chart of new articles
- Success vs failed pie chart
- Source reliability table (success rate, avg duration)
- Recent run log with status colours
- Failed run error details

---

## 📧 Email Alert Types

### Breaking News Alert
- Triggered every 15 minutes when `market_impact_score ≥ 70`
- Contains: headline, source, sentiment, direction, impact score
- HTML table format with colour coding

### Daily Summary (08:00 UTC)
- 24-hour statistics (totals, bullish/bearish counts, avg impact)
- Top 10 stories by impact score with summaries
- Top 10 trending topics with sentiment bars

### Weekly Report (Monday 09:00 UTC)
- Coverage breakdown by source
- Top 15 weekly trends with total mentions
- Week-over-week comparison ready

---

## 🔧 Configuration Reference

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | **Required.** OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model to use |
| `POSTGRES_HOST` | `postgres` | PostgreSQL host |
| `POSTGRES_DB` | `finance_monitor` | Database name |
| `POSTGRES_USER` | `finance_user` | DB username |
| `POSTGRES_PASSWORD` | `finance_pass` | DB password |
| `N8N_WEBHOOK_BASE` | `http://n8n:5678/webhook` | n8n webhook base URL |
| `BREAKING_IMPACT_THRESHOLD` | `70` | Minimum impact score for breaking alerts |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASSWORD` | — | SMTP password (use App Password for Gmail) |

### Scrapy Settings (`scrapers/settings.py`)
- `DOWNLOAD_DELAY`: 2-5s per spider (respectful crawling)
- `CONCURRENT_REQUESTS_PER_DOMAIN`: 2 max
- `AUTOTHROTTLE_ENABLED`: True (adapts to server load)
- `ROBOTSTXT_OBEY`: True

---

## 🛠️ Troubleshooting

### Airflow DAG not running
```bash
docker-compose logs airflow-scheduler
# Check for import errors in DAGs
docker exec airflow_scheduler airflow dags list
```

### Database connection issues
```bash
docker-compose logs postgres
docker exec finance_postgres pg_isready -U postgres
```

### Scrapy spider errors
```bash
python scripts/run_scrapers.py --spider reuters
cat /tmp/scrapy_reuters.log
```

### Streamlit not loading
```bash
docker-compose logs streamlit
# Check DB connectivity
docker exec finance_streamlit python -c "from database.db import init_pool; init_pool(); print('DB OK')"
```

### n8n workflow not sending emails
1. Check SMTP credentials in n8n Credentials menu
2. Verify workflow is activated (green toggle)
3. Test webhook manually:
```bash
curl -X POST http://localhost:5678/webhook/breaking-news \
  -H "Content-Type: application/json" \
  -d '{"expert_name":"Test","expert_email":"test@example.com","articles":[]}'
```

---

## 📈 Scaling Recommendations

| Concern | Solution |
|---------|----------|
| High article volume | Increase `CONCURRENT_REQUESTS` in Scrapy settings |
| OpenAI rate limits | Use `gpt-4o-mini`, implement exponential backoff (already in analyzer.py) |
| DB performance | Add `pg_partman` for time-based partitioning of `news_articles` |
| Multiple workers | Switch Airflow to `CeleryExecutor` + Redis |
| Production deployment | Add Nginx reverse proxy, SSL, secrets manager |
| Monitoring | Add Prometheus + Grafana for metrics |

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run tests: `pytest tests/ -v`
4. Commit: `git commit -m "feat: add my feature"`
5. Push and open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

**University of Central Punjab · BS Data Science · Tools and Techniques in Data Science**  
*Finance AI News & Trend Monitoring Platform*
