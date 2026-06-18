"""
scrapers/spiders/yahoo_finance_spider.py — Yahoo Finance spider
"""

import scrapy
from scrapers.items import NewsArticleItem


class YahooFinanceSpider(scrapy.Spider):
    name = "yahoo_finance"
    allowed_domains = ["finance.yahoo.com"]
    custom_settings = {"DOWNLOAD_DELAY": 2}

    start_urls = [
        "https://finance.yahoo.com/news/",
        "https://finance.yahoo.com/topic/stock-market-news/",
        "https://finance.yahoo.com/topic/economic-news/",
        "https://finance.yahoo.com/topic/earnings/",
    ]

    def parse(self, response):
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            if href.startswith("/"):
                href = f"https://finance.yahoo.com{href}"
            
            # Match article/news URLs containing finance subcategories
            is_article = (
                href.endswith(".html") or href.endswith(".html/")
            ) and (
                "/news/" in href or 
                "/articles/" in href or 
                "/personal-finance/" in href or 
                "/markets/" in href or 
                "/economy/" in href
            )
            if is_article and "/video/" not in href:
                yield scrapy.Request(href, callback=self.parse_article,
                                     errback=self.errback)

    def parse_article(self, response):
        # Prefer cover-title h1 to avoid generic page brand h1
        headline_candidates = (
            response.css("h1.cover-title::text").getall()
            or response.css("h1[data-test-locator='headline']::text").getall()
            or response.css("header h1::text").getall()
            or response.css("h1::text").getall()
        )
        headline = ""
        for h in headline_candidates:
            h_clean = h.strip()
            if h_clean and h_clean.lower() != "yahoo finance":
                headline = h_clean
                break
        if not headline and headline_candidates:
            headline = headline_candidates[0].strip()

        paragraphs = response.css(
            "div.caas-body p::text, "
            ".article-wrap p::text, "
            "[class*='body'] p::text"
        ).getall()
        full_text = " ".join(p.strip() for p in paragraphs if p.strip())

        author = (
            response.css("div.byline-attr-author::text").get()
            or response.css("span.caas-author-byline-collapse::text").get()
            or response.css("[class*='author']::text").get()
            or "Yahoo Finance"
        ).strip()

        pub_date = response.css("time::attr(datetime)").get() or ""

        category = "Finance"
        for crumb in response.css("nav[aria-label='breadcrumb'] a::text").getall():
            if crumb.strip().lower() not in ("home", "finance", "yahoo finance"):
                category = crumb.strip()
                break

        item = NewsArticleItem(
            headline=headline,
            full_text=full_text,
            author=author,
            publish_date=pub_date,
            source="Yahoo Finance",
            source_url=response.url,
            category=category,
        )
        if headline:
            yield item

    def errback(self, failure):
        status = getattr(getattr(failure.value, "response", None), "status", None)
        self.logger.warning("Request failed: %s - Status: %s - Error: %s", failure.request.url, status, repr(failure.value))


class CNBCSpider(scrapy.Spider):
    name = "cnbc"
    allowed_domains = ["cnbc.com"]
    custom_settings = {"DOWNLOAD_DELAY": 3}

    start_urls = [
        "https://www.cnbc.com/finance/",
        "https://www.cnbc.com/markets/",
        "https://www.cnbc.com/investing/",
        "https://www.cnbc.com/economy/",
    ]

    def parse(self, response):
        for link in response.css(
            "a.LatestNews-headline, "
            ".Card-titleContainer a, "
            "[class*='LatestNews'] a, "
            "div.MarketsBulletsCard a"
        ):
            href = link.attrib.get("href", "")
            if not href.startswith("http"):
                href = f"https://www.cnbc.com{href}"
            if "/video/" not in href and ".cnbc.com/" in href:
                yield scrapy.Request(href, callback=self.parse_article,
                                     errback=self.errback)

    def parse_article(self, response):
        headline = (
            response.css("h1.ArticleHeader-headline::text").get()
            or response.css("h1::text").get()
            or ""
        ).strip()

        paragraphs = response.css(
            "div.group p::text, "
            ".ArticleBody-articleBody p::text, "
            "[class*='RegularArticle-articleBody'] p::text"
        ).getall()
        full_text = " ".join(p.strip() for p in paragraphs if p.strip())

        author = (
            response.css("a[class*='Author']::text").get()
            or response.css("[class*='author']::text").get()
            or "CNBC"
        ).strip()

        pub_date = (
            response.css("time.ArticleHeader-time::attr(datetime)").get()
            or response.css("time::attr(datetime)").get()
            or ""
        )

        category_parts = response.url.replace("https://www.cnbc.com/", "").split("/")
        category = category_parts[0].replace("-", " ").title() if category_parts else "Finance"

        item = NewsArticleItem(
            headline=headline,
            full_text=full_text,
            author=author,
            publish_date=pub_date,
            source="CNBC",
            source_url=response.url,
            category=category,
        )
        if headline:
            yield item

    def errback(self, failure):
        status = getattr(getattr(failure.value, "response", None), "status", None)
        self.logger.warning("Request failed: %s - Status: %s - Error: %s", failure.request.url, status, repr(failure.value))


class MarketWatchSpider(scrapy.Spider):
    name = "marketwatch"
    allowed_domains = ["marketwatch.com"]
    custom_settings = {"DOWNLOAD_DELAY": 2}

    start_urls = [
        "https://www.marketwatch.com/latest-news",
        "https://www.marketwatch.com/economy-politics",
        "https://www.marketwatch.com/investing",
    ]

    def parse(self, response):
        for link in response.css(
            "a.link--headline, "
            ".article__headline a, "
            "[class*='headline'] a"
        ):
            href = link.attrib.get("href", "")
            if not href.startswith("http"):
                href = f"https://www.marketwatch.com{href}"
            yield scrapy.Request(href, callback=self.parse_article,
                                 errback=self.errback)

    def parse_article(self, response):
        headline = (
            response.css("h1.article__headline::text").get()
            or response.css("h1::text").get()
            or ""
        ).strip()

        paragraphs = response.css(
            ".article__body p::text, "
            ".paywall p::text, "
            "[class*='article-content'] p::text"
        ).getall()
        full_text = " ".join(p.strip() for p in paragraphs if p.strip())

        author = (
            response.css(".author--name::text").get()
            or response.css("[class*='byline']::text").get()
            or "MarketWatch"
        ).strip()

        pub_date = (
            response.css("time.timestamp--pub::attr(datetime)").get()
            or response.css("time::attr(datetime)").get()
            or ""
        )

        category_parts = response.url.replace("https://www.marketwatch.com/", "").split("/")
        category = category_parts[0].replace("-", " ").title() if category_parts else "Finance"

        item = NewsArticleItem(
            headline=headline,
            full_text=full_text,
            author=author,
            publish_date=pub_date,
            source="MarketWatch",
            source_url=response.url,
            category=category,
        )
        if headline:
            yield item

    def errback(self, failure):
        status = getattr(getattr(failure.value, "response", None), "status", None)
        self.logger.warning("Request failed: %s - Status: %s - Error: %s", failure.request.url, status, repr(failure.value))


class InvestingComSpider(scrapy.Spider):
    """
    Investing.com blocks automated scraping aggressively.
    This spider uses polite delays and respects robots.txt.
    For production consider their official API or paid data feed.
    """
    name = "investing_com"
    allowed_domains = ["investing.com"]
    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "ROBOTSTXT_OBEY": True,
    }

    start_urls = [
        "https://www.investing.com/news/stock-market-news",
        "https://www.investing.com/news/economy",
        "https://www.investing.com/news/forex-news",
    ]

    def parse(self, response):
        for link in response.css(
            "article.js-article-item a.title, "
            ".largeTitle a, "
            "[class*='articleItem'] a"
        ):
            href = link.attrib.get("href", "")
            if href.startswith("/"):
                href = f"https://www.investing.com{href}"
            yield scrapy.Request(href, callback=self.parse_article,
                                 errback=self.errback)

    def parse_article(self, response):
        headline = (
            response.css("h1.articleHeader::text").get()
            or response.css("h1::text").get()
            or ""
        ).strip()

        paragraphs = response.css(
            ".WYSIWYG.articlePage p::text, "
            "#article p::text"
        ).getall()
        full_text = " ".join(p.strip() for p in paragraphs if p.strip())

        author = (
            response.css("span.authorName::text").get()
            or "Investing.com"
        ).strip()

        pub_date = (
            response.css("time::attr(datetime)").get()
            or response.css("[class*='date']::text").get()
            or ""
        )

        item = NewsArticleItem(
            headline=headline,
            full_text=full_text,
            author=author,
            publish_date=pub_date,
            source="Investing.com",
            source_url=response.url,
            category="Finance",
        )
        if headline:
            yield item

    def errback(self, failure):
        status = getattr(getattr(failure.value, "response", None), "status", None)
        self.logger.warning("Request failed: %s - Status: %s - Error: %s", failure.request.url, status, repr(failure.value))
