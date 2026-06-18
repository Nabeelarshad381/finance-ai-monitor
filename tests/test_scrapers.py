"""
tests/test_scrapers.py
Unit tests for Scrapy items, pipelines (mocked DB), and spider output shapes.
Run: pytest tests/test_scrapers.py -v
"""

import sys, os, unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapy.http import HtmlResponse, Request
from scrapers.items import NewsArticleItem


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_response(url: str, html: str) -> HtmlResponse:
    """Create a fake Scrapy HtmlResponse for testing."""
    return HtmlResponse(
        url=url,
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request(url=url),
    )


# ── Item tests ────────────────────────────────────────────────────────────────

class TestNewsArticleItem(unittest.TestCase):
    def test_item_creation(self):
        item = NewsArticleItem(
            headline="Fed raises rates by 25bps",
            full_text="The Federal Reserve...",
            author="Jane Doe",
            publish_date="2024-01-15T10:00:00Z",
            source="Reuters",
            source_url="https://reuters.com/article/fed-rates",
            category="Monetary Policy",
        )
        self.assertEqual(item["headline"], "Fed raises rates by 25bps")
        self.assertEqual(item["source"],   "Reuters")

    def test_item_missing_field_raises(self):
        item = NewsArticleItem()
        with self.assertRaises(KeyError):
            _ = item["headline"]  # not set yet

    def test_item_fields_list(self):
        fields = list(NewsArticleItem.fields.keys())
        required = ["headline","full_text","author","publish_date",
                    "source","source_url","category"]
        for f in required:
            self.assertIn(f, fields, f"Missing field: {f}")


# ── Validation pipeline tests ─────────────────────────────────────────────────

class TestValidationPipeline(unittest.TestCase):
    def setUp(self):
        from scrapers.pipelines import ValidationPipeline
        self.pipeline = ValidationPipeline()
        self.spider   = MagicMock()

    def test_valid_item_passes(self):
        item = NewsArticleItem(
            headline="Oil prices surge",
            source_url="https://reuters.com/oil-surge",
            source="Reuters",
        )
        result = self.pipeline.process_item(item, self.spider)
        self.assertEqual(result["headline"], "Oil prices surge")

    def test_missing_headline_drops(self):
        from scrapy.exceptions import DropItem
        item = NewsArticleItem(
            source_url="https://reuters.com/something",
            source="Reuters",
        )
        with self.assertRaises(DropItem):
            self.pipeline.process_item(item, self.spider)

    def test_missing_source_url_drops(self):
        from scrapy.exceptions import DropItem
        item = NewsArticleItem(
            headline="Some news",
            source="Reuters",
        )
        with self.assertRaises(DropItem):
            self.pipeline.process_item(item, self.spider)

    def test_missing_source_drops(self):
        from scrapy.exceptions import DropItem
        item = NewsArticleItem(
            headline="Some news",
            source_url="https://reuters.com/news",
        )
        with self.assertRaises(DropItem):
            self.pipeline.process_item(item, self.spider)


# ── Deduplication pipeline tests ──────────────────────────────────────────────

class TestDuplicationPipeline(unittest.TestCase):
    def setUp(self):
        from scrapers.pipelines import DuplicationPipeline
        self.pipeline = DuplicationPipeline()
        self.spider   = MagicMock()

    @patch("scrapers.pipelines.article_exists", return_value=False)
    def test_new_article_passes(self, mock_exists):
        item = NewsArticleItem(
            headline="New article",
            source_url="https://reuters.com/new",
            source="Reuters",
        )
        result = self.pipeline.process_item(item, self.spider)
        self.assertEqual(result["headline"], "New article")

    @patch("scrapers.pipelines.article_exists", return_value=True)
    def test_duplicate_article_dropped(self, mock_exists):
        from scrapy.exceptions import DropItem
        item = NewsArticleItem(
            headline="Duplicate article",
            source_url="https://reuters.com/dup",
            source="Reuters",
        )
        with self.assertRaises(DropItem):
            self.pipeline.process_item(item, self.spider)


# ── Reuters spider parse tests ────────────────────────────────────────────────

class TestReutersSpider(unittest.TestCase):
    def setUp(self):
        from scrapers.spiders.reuters_spider import ReutersSpider
        self.spider = ReutersSpider()

    def test_parse_article_yields_item(self):
        html = """
        <html><body>
          <h1 data-testid="Heading">Oil prices hit six-month high on supply cuts</h1>
          <div data-testid="paragraph-container">
            <p>Oil prices rose sharply on Monday after OPEC+ announced supply cuts.</p>
            <p>Brent crude climbed 2.5% to $89 per barrel.</p>
          </div>
          <a rel="author">John Smith</a>
          <time datetime="2024-06-01T09:30:00Z">June 1, 2024</time>
        </body></html>
        """
        url      = "https://www.reuters.com/markets/oil-prices-high-2024-06-01/"
        response = _fake_response(url, html)
        items    = list(self.spider.parse_article(response))

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["headline"], "Oil prices hit six-month high on supply cuts")
        self.assertEqual(item["author"],   "John Smith")
        self.assertEqual(item["source"],   "Reuters")
        self.assertIn("oil prices rose sharply", item["full_text"].lower())

    def test_parse_article_empty_headline_yields_nothing(self):
        html     = "<html><body><p>Some text but no headline</p></body></html>"
        response = _fake_response("https://www.reuters.com/markets/empty/", html)
        items    = list(self.spider.parse_article(response))
        self.assertEqual(len(items), 0)


# ── Yahoo Finance spider parse tests ─────────────────────────────────────────

class TestYahooFinanceSpider(unittest.TestCase):
    def setUp(self):
        from scrapers.spiders.finance_spiders import YahooFinanceSpider
        self.spider = YahooFinanceSpider()

    def test_parse_article_yields_item(self):
        html = """
        <html><body>
          <h1 data-test-locator="headline">Tesla beats Q2 earnings expectations</h1>
          <div class="caas-body">
            <p>Tesla reported record quarterly profits, beating analyst estimates.</p>
          </div>
          <span class="caas-author-byline-collapse">Reuters Staff</span>
          <time datetime="2024-07-23T14:00:00Z"></time>
        </body></html>
        """
        url      = "https://finance.yahoo.com/news/tesla-beats-q2-earnings-140000123.html"
        response = _fake_response(url, html)
        items    = list(self.spider.parse_article(response))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "Yahoo Finance")
        self.assertIn("tesla", items[0]["headline"].lower())

    def test_missing_headline_skipped(self):
        html     = "<html><body><p>No headline here.</p></body></html>"
        response = _fake_response("https://finance.yahoo.com/news/empty/", html)
        items    = list(self.spider.parse_article(response))
        self.assertEqual(len(items), 0)


# ── CNBC spider tests ─────────────────────────────────────────────────────────

class TestCNBCSpider(unittest.TestCase):
    def setUp(self):
        from scrapers.spiders.finance_spiders import CNBCSpider
        self.spider = CNBCSpider()

    def test_parse_article(self):
        html = """
        <html><body>
          <h1 class="ArticleHeader-headline">S&amp;P 500 reaches record high</h1>
          <div class="group"><p>Stocks surged to record highs as inflation data cooled.</p></div>
          <a class="Author-authorName">CNBC Markets Team</a>
          <time class="ArticleHeader-time" datetime="2024-08-15T16:30:00Z"></time>
        </body></html>
        """
        url      = "https://www.cnbc.com/markets/sp500-record-high-2024/"
        response = _fake_response(url, html)
        items    = list(self.spider.parse_article(response))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "CNBC")


# ── DB helper tests ───────────────────────────────────────────────────────────

class TestUrlHash(unittest.TestCase):
    def test_hash_length(self):
        from database.db import url_hash
        self.assertEqual(len(url_hash("https://example.com")), 64)

    def test_hash_deterministic(self):
        from database.db import url_hash
        url = "https://reuters.com/article/test"
        self.assertEqual(url_hash(url), url_hash(url))

    def test_different_urls_different_hashes(self):
        from database.db import url_hash
        self.assertNotEqual(
            url_hash("https://reuters.com/a"),
            url_hash("https://reuters.com/b"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
