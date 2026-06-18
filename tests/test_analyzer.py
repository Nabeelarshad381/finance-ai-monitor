"""
tests/test_analyzer.py — Unit tests for the AI analysis engine
Run: pytest tests/ -v
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_engine.analyzer import _validate_and_clean, _freq_count_trending


class TestValidateAndClean(unittest.TestCase):
    def test_clamps_sentiment_score(self):
        result = _validate_and_clean({
            "sentiment_score": 5.0,
            "market_impact_score": 200.0,
            "confidence": 2.0,
            "sentiment_label": "positive",
            "market_direction": "bullish",
        })
        self.assertLessEqual(result["sentiment_score"], 1.0)
        self.assertLessEqual(result["market_impact_score"], 100.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_uppercase_labels(self):
        result = _validate_and_clean({
            "sentiment_label": "positive",
            "market_direction": "bullish",
            "sentiment_score": 0.5,
            "market_impact_score": 50.0,
            "confidence": 0.8,
        })
        self.assertEqual(result["sentiment_label"], "POSITIVE")
        self.assertEqual(result["market_direction"], "BULLISH")

    def test_ticker_uppercase(self):
        result = _validate_and_clean({
            "sentiment_label": "NEUTRAL",
            "market_direction": "NEUTRAL",
            "sentiment_score": 0.0,
            "market_impact_score": 30.0,
            "confidence": 0.6,
            "mentioned_tickers": ["aapl", "tsla", "nvda"],
        })
        self.assertEqual(result["mentioned_tickers"], ["AAPL", "TSLA", "NVDA"])

    def test_key_topics_capped_at_6(self):
        result = _validate_and_clean({
            "sentiment_label": "NEUTRAL",
            "market_direction": "NEUTRAL",
            "sentiment_score": 0.0,
            "market_impact_score": 10.0,
            "confidence": 0.5,
            "key_topics": ["a", "b", "c", "d", "e", "f", "g", "h"],
        })
        self.assertLessEqual(len(result["key_topics"]), 6)

    def test_missing_fields_default(self):
        result = _validate_and_clean({})
        self.assertEqual(result["sentiment_label"], "NEUTRAL")
        self.assertEqual(result["market_direction"], "NEUTRAL")
        self.assertEqual(result["sentiment_score"], 0.0)
        self.assertEqual(result["mentioned_tickers"], [])


class TestFreqCountTrending(unittest.TestCase):
    def setUp(self):
        self.analyses = [
            {
                "mentioned_tickers": ["AAPL", "MSFT"],
                "mentioned_sectors": ["Technology"],
                "key_topics": ["AI", "earnings"],
                "sentiment_score": 0.5,
                "market_direction": "BULLISH",
            },
            {
                "mentioned_tickers": ["AAPL", "TSLA"],
                "mentioned_sectors": ["Technology", "Energy"],
                "key_topics": ["AI", "interest rates"],
                "sentiment_score": -0.2,
                "market_direction": "BEARISH",
            },
            {
                "mentioned_tickers": ["AAPL"],
                "mentioned_sectors": ["Technology"],
                "key_topics": ["AI"],
                "sentiment_score": 0.8,
                "market_direction": "BULLISH",
            },
        ]

    def test_aapl_is_top(self):
        results = _freq_count_trending(self.analyses)
        topics = [r["topic"] for r in results]
        self.assertIn("AAPL", topics)
        aapl = next(r for r in results if r["topic"] == "AAPL")
        self.assertEqual(aapl["mention_count"], 3)

    def test_ai_topic_counted(self):
        results = _freq_count_trending(self.analyses)
        ai = next((r for r in results if r["topic"] == "AI"), None)
        self.assertIsNotNone(ai)
        self.assertEqual(ai["mention_count"], 3)

    def test_avg_sentiment_computed(self):
        results = _freq_count_trending(self.analyses)
        aapl = next(r for r in results if r["topic"] == "AAPL")
        expected = round((0.5 + -0.2 + 0.8) / 3, 4)
        self.assertAlmostEqual(aapl["avg_sentiment"], expected, places=3)

    def test_empty_input(self):
        results = _freq_count_trending([])
        self.assertEqual(results, [])

    def test_max_15_results(self):
        # Generate 20 unique tickers
        big = [{"mentioned_tickers": [f"T{i}"], "mentioned_sectors": [],
                "key_topics": [], "sentiment_score": 0, "market_direction": "NEUTRAL"}
               for i in range(20)]
        results = _freq_count_trending(big)
        self.assertLessEqual(len(results), 15)


class TestDatabaseUrl(unittest.TestCase):
    def test_url_hash_is_deterministic(self):
        from database.db import url_hash
        url = "https://www.reuters.com/markets/test-article-123"
        self.assertEqual(url_hash(url), url_hash(url))
        self.assertEqual(len(url_hash(url)), 64)

    def test_different_urls_different_hashes(self):
        from database.db import url_hash
        self.assertNotEqual(
            url_hash("https://www.reuters.com/article/1"),
            url_hash("https://www.reuters.com/article/2"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
