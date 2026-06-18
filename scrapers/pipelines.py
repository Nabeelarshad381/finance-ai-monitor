"""
scrapers/pipelines.py — Scrapy item pipelines

Pipeline order:
  1. ValidationPipeline   — drop items missing required fields
  2. DuplicationPipeline  — check DB for existing URL hash
  3. PostgresPipeline      — insert into PostgreSQL
"""

import logging
from datetime import datetime, timezone

from itemadapter import ItemAdapter

from database.db import article_exists, insert_article

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """Drop items that lack mandatory fields."""

    REQUIRED = ("headline", "source_url", "source")

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        for field in self.REQUIRED:
            if not adapter.get(field):
                spider.logger.warning(
                    "Dropping item — missing '%s': %s",
                    field,
                    adapter.get("source_url", "N/A"),
                )
                raise DropItem(f"Missing required field: {field}")
        return item


class DuplicationPipeline:
    """Drop already-scraped articles."""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = adapter.get("source_url", "")
        if article_exists(url):
            raise DropItem(f"Duplicate: {url}")
        return item


class PostgresPipeline:
    """Persist validated, unique items to PostgreSQL."""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)

        # Normalise publish_date
        pub_date = adapter.get("publish_date")
        if isinstance(pub_date, str) and pub_date:
            try:
                from dateutil import parser as dtparser
                pub_date = dtparser.parse(pub_date)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except Exception:
                pub_date = None

        data = {
            "headline":     adapter.get("headline", "")[:1000],
            "full_text":    adapter.get("full_text", ""),
            "author":       adapter.get("author", ""),
            "publish_date": pub_date,
            "source":       adapter.get("source", ""),
            "source_url":   adapter.get("source_url", ""),
            "category":     adapter.get("category", "Finance"),
        }

        article_id = insert_article(data)
        if article_id:
            spider.logger.debug("Inserted article %s", article_id)
        return item


# Import at the bottom to avoid circular import issues in Scrapy
from scrapy.exceptions import DropItem  # noqa: E402
