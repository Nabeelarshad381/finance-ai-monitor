"""
tests/test_db.py
Unit tests for database helper functions (using mocks — no real DB needed).
Run: pytest tests/test_db.py -v
"""

import sys, os, unittest
from unittest.mock import patch, MagicMock, call
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestUrlHash(unittest.TestCase):
    """url_hash is pure Python — no DB needed."""

    def setUp(self):
        from database.db import url_hash
        self.url_hash = url_hash

    def test_sha256_length(self):
        self.assertEqual(len(self.url_hash("https://example.com")), 64)

    def test_hex_characters_only(self):
        h = self.url_hash("https://reuters.com/article/test-123")
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_deterministic(self):
        url = "https://cnbc.com/markets/news-article-456/"
        self.assertEqual(self.url_hash(url), self.url_hash(url))

    def test_collision_resistance(self):
        urls = [f"https://reuters.com/article/{i}" for i in range(100)]
        hashes = [self.url_hash(u) for u in urls]
        self.assertEqual(len(set(hashes)), 100, "Hash collision detected!")

    def test_empty_string(self):
        h = self.url_hash("")
        self.assertEqual(len(h), 64)


class TestInsertArticle(unittest.TestCase):
    """Test insert_article with mocked DB."""

    @patch("database.db.article_exists", return_value=False)
    @patch("database.db.get_cursor")
    def test_insert_new_article_returns_id(self, mock_get_cursor, mock_exists):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"id": "test-uuid-1234"}
        mock_get_cursor.return_value = mock_cursor

        from database.db import insert_article
        result = insert_article({
            "headline":     "Test headline",
            "full_text":    "Full text here.",
            "author":       "Test Author",
            "publish_date": None,
            "source":       "Reuters",
            "source_url":   "https://reuters.com/test-article-001",
            "category":     "Finance",
        })
        self.assertEqual(result, "test-uuid-1234")

    @patch("database.db.article_exists", return_value=True)
    def test_insert_duplicate_returns_none(self, mock_exists):
        from database.db import insert_article
        result = insert_article({
            "headline":   "Duplicate",
            "source_url": "https://reuters.com/dup",
            "source":     "Reuters",
        })
        self.assertIsNone(result)


class TestGetUnprocessedArticles(unittest.TestCase):
    @patch("database.db.get_cursor")
    def test_returns_list_of_dicts(self, mock_get_cursor):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {"id": "abc", "headline": "Article 1", "full_text": "Text",
             "source": "CNBC", "category": "Finance", "publish_date": None},
            {"id": "def", "headline": "Article 2", "full_text": "Text 2",
             "source": "Reuters", "category": "Markets", "publish_date": None},
        ]
        mock_get_cursor.return_value = mock_cursor

        from database.db import get_unprocessed_articles
        result = get_unprocessed_articles(limit=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["headline"], "Article 1")

    @patch("database.db.get_cursor")
    def test_empty_result(self, mock_get_cursor):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_get_cursor.return_value = mock_cursor

        from database.db import get_unprocessed_articles
        result = get_unprocessed_articles()
        self.assertEqual(result, [])


class TestInsertAnalysis(unittest.TestCase):
    @patch("database.db.get_cursor")
    def test_insert_analysis_calls_execute(self, mock_get_cursor):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value = mock_cursor

        from database.db import insert_analysis
        insert_analysis({
            "article_id":          "test-uuid",
            "sentiment_label":     "POSITIVE",
            "sentiment_score":     0.75,
            "market_direction":    "BULLISH",
            "market_impact_score": 65.0,
            "summary":             "Test summary",
            "key_topics":          ["AI", "earnings"],
            "mentioned_tickers":   ["AAPL"],
            "mentioned_sectors":   ["Technology"],
            "confidence":          0.9,
        })
        self.assertTrue(mock_cursor.execute.called)

    @patch("database.db.get_cursor")
    def test_mark_article_processed(self, mock_get_cursor):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value = mock_cursor

        from database.db import mark_article_processed
        mark_article_processed("some-uuid")
        mock_cursor.execute.assert_called_once()
        args = mock_cursor.execute.call_args[0]
        self.assertIn("is_processed = TRUE", args[0])
        self.assertEqual(args[1], ("some-uuid",))


class TestLogAlert(unittest.TestCase):
    @patch("database.db.get_cursor")
    def test_log_alert_sent(self, mock_get_cursor):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value = mock_cursor

        from database.db import log_alert
        log_alert(
            expert_id="expert-uuid",
            alert_type="BREAKING",
            subject="Breaking: Fed raises rates",
            body_preview="The Federal Reserve...",
            status="SENT",
        )
        self.assertTrue(mock_cursor.execute.called)

    @patch("database.db.get_cursor")
    def test_log_alert_failed(self, mock_get_cursor):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value = mock_cursor

        from database.db import log_alert
        log_alert(
            expert_id="expert-uuid",
            alert_type="DAILY_SUMMARY",
            subject="Daily Report",
            body_preview="Summary here...",
            status="FAILED",
            error_message="SMTP connection refused",
        )
        call_args = mock_cursor.execute.call_args[0][1]
        self.assertIn("FAILED", call_args)
        self.assertIn("SMTP connection refused", call_args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
