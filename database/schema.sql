-- ============================================================
-- Finance AI News & Trend Monitoring Platform
-- PostgreSQL Database Schema
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fast text search

-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS news_articles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    headline        TEXT NOT NULL,
    full_text       TEXT,
    author          TEXT,
    publish_date    TIMESTAMPTZ,
    source          VARCHAR(100) NOT NULL,
    source_url      TEXT,
    category        VARCHAR(100),
    url_hash        CHAR(64) UNIQUE NOT NULL,  -- SHA-256 of URL for dedup
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    is_processed    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_articles_source        ON news_articles(source);
CREATE INDEX idx_articles_category      ON news_articles(category);
CREATE INDEX idx_articles_publish_date  ON news_articles(publish_date DESC);
CREATE INDEX idx_articles_processed     ON news_articles(is_processed);
CREATE INDEX idx_articles_headline_trgm ON news_articles USING gin(headline gin_trgm_ops);
CREATE INDEX idx_articles_fulltext_trgm ON news_articles USING gin(full_text gin_trgm_ops);

-- ============================================================
-- AI ANALYSIS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS article_analysis (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id          UUID NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
    sentiment_label     VARCHAR(20),        -- POSITIVE / NEGATIVE / NEUTRAL
    sentiment_score     NUMERIC(5,4),       -- -1.0 to 1.0
    market_direction    VARCHAR(10),        -- BULLISH / BEARISH / NEUTRAL
    market_impact_score NUMERIC(5,2),       -- 0-100
    summary             TEXT,
    key_topics          TEXT[],
    mentioned_tickers   TEXT[],
    mentioned_sectors   TEXT[],
    confidence          NUMERIC(4,3),       -- 0-1 model confidence
    analyzed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_analysis_article ON article_analysis(article_id);
CREATE INDEX idx_analysis_sentiment      ON article_analysis(sentiment_label);
CREATE INDEX idx_analysis_direction      ON article_analysis(market_direction);
CREATE INDEX idx_analysis_impact         ON article_analysis(market_impact_score DESC);

-- ============================================================
-- TRENDING TOPICS
-- ============================================================

CREATE TABLE IF NOT EXISTS trending_topics (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic           VARCHAR(255) NOT NULL,
    topic_type      VARCHAR(50),        -- STOCK / SECTOR / MACRO / EVENT / COMPANY
    mention_count   INTEGER DEFAULT 0,
    avg_sentiment   NUMERIC(5,4),
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    calculated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trending_count      ON trending_topics(mention_count DESC);
CREATE INDEX idx_trending_window     ON trending_topics(window_start, window_end);
CREATE INDEX idx_trending_type       ON trending_topics(topic_type);

-- ============================================================
-- FINANCE EXPERTS (ALERT SUBSCRIBERS)
-- ============================================================

CREATE TABLE IF NOT EXISTS finance_experts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name           VARCHAR(200) NOT NULL,
    email               VARCHAR(255) UNIQUE NOT NULL,
    organization        VARCHAR(200),
    role                VARCHAR(100),
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_experts_email  ON finance_experts(email);
CREATE INDEX idx_experts_active ON finance_experts(is_active);

-- ============================================================
-- ALERT PREFERENCES
-- ============================================================

CREATE TABLE IF NOT EXISTS alert_preferences (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    expert_id               UUID NOT NULL REFERENCES finance_experts(id) ON DELETE CASCADE,
    alert_type              VARCHAR(50) NOT NULL,   -- BREAKING / DAILY_SUMMARY / WEEKLY_REPORT / THRESHOLD
    sentiment_threshold     NUMERIC(5,4) DEFAULT 0.7,
    impact_threshold        NUMERIC(5,2) DEFAULT 70.0,
    preferred_sources       TEXT[],
    preferred_categories    TEXT[],
    preferred_tickers       TEXT[],
    send_breaking_news      BOOLEAN DEFAULT TRUE,
    send_daily_summary      BOOLEAN DEFAULT TRUE,
    send_weekly_report      BOOLEAN DEFAULT TRUE,
    daily_summary_time      TIME DEFAULT '08:00:00',
    weekly_report_day       SMALLINT DEFAULT 1,     -- 1=Monday
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_prefs_expert_type ON alert_preferences(expert_id, alert_type);

-- ============================================================
-- ALERT LOGS
-- ============================================================

CREATE TABLE IF NOT EXISTS alert_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    expert_id       UUID REFERENCES finance_experts(id) ON DELETE SET NULL,
    alert_type      VARCHAR(50),
    subject         TEXT,
    body_preview    TEXT,
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    status          VARCHAR(20) DEFAULT 'SENT',     -- SENT / FAILED / PENDING
    error_message   TEXT
);

CREATE INDEX idx_logs_expert  ON alert_logs(expert_id);
CREATE INDEX idx_logs_sent    ON alert_logs(sent_at DESC);
CREATE INDEX idx_logs_status  ON alert_logs(status);

-- ============================================================
-- SCRAPE RUNS (for monitoring)
-- ============================================================

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(100) NOT NULL,
    run_start       TIMESTAMPTZ DEFAULT NOW(),
    run_end         TIMESTAMPTZ,
    articles_found  INTEGER DEFAULT 0,
    articles_new    INTEGER DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'RUNNING',  -- RUNNING / SUCCESS / FAILED
    error_message   TEXT
);

CREATE INDEX idx_runs_source ON scrape_runs(source);
CREATE INDEX idx_runs_start  ON scrape_runs(run_start DESC);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_articles_updated
    BEFORE UPDATE ON news_articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_experts_updated
    BEFORE UPDATE ON finance_experts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_prefs_updated
    BEFORE UPDATE ON alert_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- SEED DATA — sample experts
-- ============================================================

INSERT INTO finance_experts (full_name, email, organization, role) VALUES
('Alice Morgan',  'alice@financelab.io',  'FinanceLab',       'Senior Analyst'),
('Bob Chen',      'bob@hedgefund.io',     'Apex Hedge Fund',  'Portfolio Manager'),
('Sara Ali',      'sara@tradingco.io',    'TradingCo',        'Quant Researcher')
ON CONFLICT DO NOTHING;

INSERT INTO alert_preferences (expert_id, alert_type, sentiment_threshold, impact_threshold)
SELECT id, 'BREAKING',       0.65, 65.0 FROM finance_experts WHERE email = 'alice@financelab.io'
ON CONFLICT DO NOTHING;

INSERT INTO alert_preferences (expert_id, alert_type, send_daily_summary, send_weekly_report)
SELECT id, 'DAILY_SUMMARY',  TRUE, TRUE  FROM finance_experts WHERE email = 'bob@hedgefund.io'
ON CONFLICT DO NOTHING;
