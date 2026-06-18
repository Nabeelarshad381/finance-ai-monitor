"""
ai_engine/analyzer.py — AI analysis using OpenAI API
Performs: sentiment analysis, bullish/bearish detection,
market impact scoring, topic detection, article summarization.
"""

import json
import logging
import os
import re
import time
from typing import Dict, Any, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# ── OpenAI client ─────────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = os.getenv("OPENAI_MODEL", "gpt-4o-mini")   # fast & cheap default
_use_mock_fallback = False


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior financial analyst AI.
Analyse finance news articles and return a JSON object with EXACTLY these keys:

{
  "sentiment_label":     "POSITIVE" | "NEGATIVE" | "NEUTRAL",
  "sentiment_score":     float between -1.0 (most negative) and 1.0 (most positive),
  "market_direction":    "BULLISH" | "BEARISH" | "NEUTRAL",
  "market_impact_score": float between 0 (no impact) and 100 (extreme impact),
  "summary":             "2-3 sentence plain-English summary",
  "key_topics":          ["topic1", "topic2", ...],          // max 6
  "mentioned_tickers":   ["AAPL", "TSLA", ...],              // stock symbols only
  "mentioned_sectors":   ["Technology", "Energy", ...],      // standard sector names
  "confidence":          float between 0.0 and 1.0
}

Rules:
- BULLISH = article signals rising prices / positive outlook
- BEARISH = article signals falling prices / negative outlook
- market_impact_score: breaking news/Fed decisions = 80-100, routine = 10-30
- Return ONLY valid JSON with no markdown fences or preamble
"""


# ── Core analyser ──────────────────────────────────────────────────────────────

def analyse_article(headline: str, full_text: str,
                    source: str = "", category: str = "") -> Optional[Dict[str, Any]]:
    """
    Analyse a single article using GPT.
    Returns a dict matching the DB schema or None on failure.
    """
    global _use_mock_fallback
    if _use_mock_fallback:
        try:
            return _mock_analyse_article(headline, full_text, source, category)
        except Exception as mock_exc:
            logger.error("Mock analysis fallback failed: %s", mock_exc)
            return None

    # Truncate to avoid token limits
    text_snippet = (full_text or "")[:3000]
    user_message = (
        f"Source: {source}\nCategory: {category}\n"
        f"Headline: {headline}\n\nArticle text:\n{text_snippet}"
    )

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.1,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)
            return _validate_and_clean(result)

        except json.JSONDecodeError as exc:
            logger.warning("JSON decode error (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:
            logger.warning("OpenAI error (attempt %d): %s", attempt + 1, exc)
            exc_str = str(exc).lower()
            if "quota" in exc_str or "api_key" in exc_str or "auth" in exc_str or "billing" in exc_str:
                logger.warning("Critical API error detected. Enabling mock fallback for all remaining articles.")
                _use_mock_fallback = True
                break
            
            if "rate_limit" in exc_str:
                time.sleep(60)
            else:
                time.sleep(5)

    logger.error("Failed to analyse article after 3 attempts, falling back to mock: %s", headline[:60])
    try:
        return _mock_analyse_article(headline, full_text, source, category)
    except Exception as mock_exc:
        logger.error("Mock analysis fallback failed: %s", mock_exc)
        return None


def _mock_analyse_article(headline: str, full_text: str, source: str = "", category: str = "") -> Dict[str, Any]:
    text = f"{headline} {full_text or ''}".lower()
    
    # 1. Sentiment analysis
    pos_words = ["growth", "gain", "profit", "surpass", "bullish", "rise", "climb", "beat", "success", "positive", "high", "up"]
    neg_words = ["drop", "fall", "decline", "loss", "bearish", "slump", "deficit", "miss", "warn", "negative", "low", "down"]
    
    pos_count = sum(text.count(w) for w in pos_words)
    neg_count = sum(text.count(w) for w in neg_words)
    
    if pos_count > neg_count:
        sentiment_label = "POSITIVE"
        sentiment_score = min(1.0, 0.1 * (pos_count - neg_count))
        market_direction = "BULLISH"
    elif neg_count > pos_count:
        sentiment_label = "NEGATIVE"
        sentiment_score = max(-1.0, -0.1 * (neg_count - pos_count))
        market_direction = "BEARISH"
    else:
        sentiment_label = "NEUTRAL"
        sentiment_score = 0.0
        market_direction = "NEUTRAL"
        
    # 2. Market impact score
    impact_words = ["fed", "interest rate", "rate hike", "cpi", "inflation", "gdp", "earnings", "sec", "lawsuit", "merger"]
    impact_count = sum(text.count(w) for w in impact_words)
    market_impact_score = min(95.0, 15.0 + 10.0 * impact_count)
    
    # 3. Mentioned tickers
    common_tickers = ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "JPM", "NFLX", "AMD", "DIS", "BABA"]
    mentioned_tickers = []
    search_text = f"{headline} {full_text or ''}"
    for ticker in common_tickers:
        if re.search(r'\b' + ticker + r'\b', search_text):
            mentioned_tickers.append(ticker)
            
    # 4. Mentioned sectors
    sector_keywords = {
        "Technology": ["tech", "software", "ai", "semiconductor", "chip", "computer", "cloud"],
        "Financials": ["bank", "finance", "credit", "insurance", "loan", "investment"],
        "Energy": ["oil", "gas", "energy", "petroleum", "solar", "wind", "coal"],
        "Healthcare": ["health", "medical", "drug", "pharma", "vaccine", "biotech"],
        "Consumer Discretionary": ["retail", "auto", "car", "travel", "entertainment", "movie"],
    }
    mentioned_sectors = []
    for sector, keywords in sector_keywords.items():
        if any(w in text for w in keywords):
            mentioned_sectors.append(sector)
            
    # 5. Key topics
    topic_keywords = {
        "Monetary Policy": ["fed", "powell", "interest rate", "rate hike", "central bank"],
        "Earnings": ["earnings", "revenue", "profit", "quarter", "report"],
        "Inflation": ["inflation", "cpi", "cpi", "prices"],
        "M&A": ["merger", "acquisition", "buyout", "acquire"],
        "Stock Market": ["stocks", "market", "nasdaq", "dow", "s&p"],
    }
    key_topics = []
    for topic, keywords in topic_keywords.items():
        if any(w in text for w in keywords):
            key_topics.append(topic)
    if not key_topics and category:
        key_topics.append(category)
    if not key_topics:
        key_topics.append("Market News")
        
    # 6. Summary
    sentences = re.split(r'\. |\? |\! ', headline + ". " + (full_text or ""))
    sentences = [s.strip() for s in sentences if s.strip()]
    summary = ". ".join(sentences[:2])
    if len(summary) > 200:
        summary = summary[:197] + "..."
    if not summary:
        summary = f"News analysis for headline: {headline} from {source}."
        
    return {
        "sentiment_label": sentiment_label,
        "sentiment_score": sentiment_score,
        "market_direction": market_direction,
        "market_impact_score": market_impact_score,
        "summary": summary,
        "key_topics": key_topics[:6],
        "mentioned_tickers": mentioned_tickers[:10],
        "mentioned_sectors": mentioned_sectors[:5],
        "confidence": 0.85
    }


def _validate_and_clean(data: Dict) -> Dict:
    """Clamp numeric fields and normalise labels."""
    data["sentiment_label"]   = data.get("sentiment_label", "NEUTRAL").upper()
    data["market_direction"]  = data.get("market_direction", "NEUTRAL").upper()
    data["sentiment_score"]   = max(-1.0, min(1.0,  float(data.get("sentiment_score", 0.0))))
    data["market_impact_score"] = max(0.0, min(100.0, float(data.get("market_impact_score", 0.0))))
    data["confidence"]        = max(0.0, min(1.0,  float(data.get("confidence", 0.5))))
    data["key_topics"]        = data.get("key_topics", [])[:6]
    data["mentioned_tickers"] = [t.upper() for t in data.get("mentioned_tickers", [])][:10]
    data["mentioned_sectors"] = data.get("mentioned_sectors", [])[:5]
    data["summary"]           = data.get("summary", "")[:1000]
    return data


# ── Trending topics detection ──────────────────────────────────────────────────

TRENDING_SYSTEM_PROMPT = """You are a financial trend analyst.
Given a JSON list of recent news analysis results, identify the top trending topics.

Return a JSON array of objects with EXACTLY these keys:
[
  {
    "topic":        "topic name (company, ticker, macro event, etc.)",
    "topic_type":   "STOCK" | "SECTOR" | "MACRO" | "EVENT" | "COMPANY",
    "mention_count": integer,
    "avg_sentiment": float -1.0 to 1.0
  },
  ...
]

Return the top 15 trends ordered by mention_count DESC.
Return ONLY valid JSON array, no markdown.
"""


def detect_trending_topics(analyses: List[Dict]) -> List[Dict]:
    """
    Takes a list of article analysis dicts and detects trending topics via GPT.
    Fallback: simple frequency counter if OpenAI fails.
    """
    if not analyses:
        return []

    # Build a compact summary to send
    compact = [
        {
            "topics":   a.get("key_topics", []),
            "tickers":  a.get("mentioned_tickers", []),
            "sectors":  a.get("mentioned_sectors", []),
            "sentiment": a.get("sentiment_score", 0),
            "direction": a.get("market_direction", "NEUTRAL"),
        }
        for a in analyses[:100]  # cap at 100 articles
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": TRENDING_SYSTEM_PROMPT},
                {"role": "user",   "content": json.dumps(compact)},
            ],
            temperature=0.1,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        # GPT sometimes wraps the array in {"trends": [...]}
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        for v in parsed.values():
            if isinstance(v, list):
                return v
    except Exception as exc:
        logger.warning("Trending topics GPT call failed: %s", exc)

    # ── Fallback: frequency count ──
    return _freq_count_trending(analyses)


def _freq_count_trending(analyses: List[Dict]) -> List[Dict]:
    from collections import Counter, defaultdict

    counts  = Counter()
    sents   = defaultdict(list)
    types   = {}

    for a in analyses:
        for t in a.get("mentioned_tickers", []):
            counts[t] += 1
            sents[t].append(a.get("sentiment_score", 0))
            types[t] = "STOCK"
        for s in a.get("mentioned_sectors", []):
            counts[s] += 1
            sents[s].append(a.get("sentiment_score", 0))
            types[s] = "SECTOR"
        for k in a.get("key_topics", []):
            counts[k] += 1
            sents[k].append(a.get("sentiment_score", 0))
            types.setdefault(k, "MACRO")

    results = []
    for topic, count in counts.most_common(15):
        avg = sum(sents[topic]) / len(sents[topic]) if sents[topic] else 0
        results.append({
            "topic":         topic,
            "topic_type":    types.get(topic, "MACRO"),
            "mention_count": count,
            "avg_sentiment": round(avg, 4),
        })
    return results


# ── Batch processor ───────────────────────────────────────────────────────────

def batch_analyse(articles: List[Dict], delay: float = 0.5) -> List[Dict]:
    """
    Analyse a batch of articles.
    Returns list of {article_id, ...analysis_fields}.
    """
    results = []
    for art in articles:
        analysis = analyse_article(
            headline  = art.get("headline", ""),
            full_text = art.get("full_text", ""),
            source    = art.get("source", ""),
            category  = art.get("category", ""),
        )
        if analysis:
            analysis["article_id"] = str(art["id"])
            results.append(analysis)
        time.sleep(delay)
    return results


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test = analyse_article(
        headline  = "Federal Reserve raises interest rates by 25 basis points amid inflation fears",
        full_text = "The Federal Reserve raised benchmark interest rates by a quarter point on Wednesday, "
                    "signalling more hikes to come as inflation remains elevated. Markets fell sharply "
                    "following the announcement, with the S&P 500 dropping 1.5%.",
        source    = "Reuters",
        category  = "Monetary Policy",
    )
    print(json.dumps(test, indent=2))
