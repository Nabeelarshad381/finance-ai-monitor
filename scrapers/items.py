# scrapers/items.py — Scrapy item definitions

import scrapy


class NewsArticleItem(scrapy.Item):
    headline        = scrapy.Field()
    full_text       = scrapy.Field()
    author          = scrapy.Field()
    publish_date    = scrapy.Field()   # ISO string — converted in pipeline
    source          = scrapy.Field()
    source_url      = scrapy.Field()
    category        = scrapy.Field()
