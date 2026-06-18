"""
scrapers/spiders/reuters_spider.py — Reuters Finance spider
"""

import scrapy
from scrapers.items import NewsArticleItem


class ReutersSpider(scrapy.Spider):
    name = "reuters"
    allowed_domains = ["reuters.com"]
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
    }

    start_urls = [
        "https://www.reuters.com/finance/",
        "https://www.reuters.com/business/finance/",
        "https://www.reuters.com/markets/",
    ]

    def parse(self, response):
        # Article links on listing pages
        for link in response.css(
            "a[data-testid='Heading'], "
            "a.story-card__heading__link, "
            "a[class*='heading'], "
            "[class*='article-list'] a"
        ):
            url = link.attrib.get("href", "")
            if url.startswith("/"):
                url = f"https://www.reuters.com{url}"
            if url and "/article/" in url or "/markets/" in url or "/business/" in url:
                yield scrapy.Request(url, callback=self.parse_article)

        # Pagination
        next_page = response.css("a[rel='next']::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_article(self, response):
        item = NewsArticleItem()

        headline = (
            response.css("h1[data-testid='Heading']::text").get()
            or response.css("h1::text").get()
            or ""
        ).strip()

        paragraphs = response.css(
            "[data-testid='paragraph-container'] p::text, "
            ".article-body p::text, "
            "[class*='text__text'] p::text"
        ).getall()
        full_text = " ".join(p.strip() for p in paragraphs if p.strip())

        author = (
            response.css("a[rel='author']::text").get()
            or response.css("[class*='author']::text").get()
            or "Reuters"
        ).strip()

        pub_date = (
            response.css("time::attr(datetime)").get()
            or response.css("[class*='date']::attr(datetime)").get()
            or ""
        )

        category = response.url.split("/")[4] if len(response.url.split("/")) > 4 else "Finance"

        item["headline"]    = headline
        item["full_text"]   = full_text
        item["author"]      = author
        item["publish_date"]= pub_date
        item["source"]      = "Reuters"
        item["source_url"]  = response.url
        item["category"]    = category.capitalize()

        if item["headline"]:
            yield item
