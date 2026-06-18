"""
scrapers/selenium/dynamic_scraper.py
Handles JavaScript-heavy pages using Selenium + undetected-chromedriver.
Used for Bloomberg and any site that blocks standard Scrapy requests.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from database.db import insert_article, article_exists

logger = logging.getLogger(__name__)


# ── Driver factory ─────────────────────────────────────────────────────────────

def _make_driver(headless: bool = True) -> uc.Chrome:
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


# ── Base scraper ───────────────────────────────────────────────────────────────

class SeleniumScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver: Optional[uc.Chrome] = None

    def __enter__(self):
        self.driver = _make_driver(self.headless)
        return self

    def __exit__(self, *_):
        if self.driver:
            self.driver.quit()

    def _get(self, url: str, wait_css: str = None, timeout: int = 15) -> Optional[BeautifulSoup]:
        try:
            self.driver.get(url)
            if wait_css:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
                )
            time.sleep(1.5)  # let JS settle
            return BeautifulSoup(self.driver.page_source, "lxml")
        except TimeoutException:
            logger.warning("Timeout loading: %s", url)
        except WebDriverException as exc:
            logger.warning("WebDriver error on %s: %s", url, exc)
        return None

    def _scroll_to_bottom(self, pauses: int = 3, pause_time: float = 1.5):
        for _ in range(pauses):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause_time)


# ── Bloomberg scraper ──────────────────────────────────────────────────────────

class BloombergScraper(SeleniumScraper):
    """
    Bloomberg requires JS rendering + login for full articles.
    This scraper collects headlines and summaries from public pages.
    Full text requires a Bloomberg Terminal or API subscription.
    """

    INDEX_URLS = [
        "https://www.bloomberg.com/markets",
        "https://www.bloomberg.com/technology",
        "https://www.bloomberg.com/economics",
    ]

    def scrape(self) -> List[Dict]:
        articles = []
        for url in self.INDEX_URLS:
            soup = self._get(url, wait_css="article, [class*='story']")
            if not soup:
                continue
            links = soup.select(
                "a[class*='story-package-module'], "
                "a[class*='headline'], "
                "article a"
            )
            for tag in links[:15]:  # top 15 per page
                href = tag.get("href", "")
                if not href.startswith("http"):
                    href = f"https://www.bloomberg.com{href}"
                if not href or "/news/" not in href:
                    continue
                if article_exists(href):
                    continue
                article = self._parse_article(href)
                if article:
                    articles.append(article)
                time.sleep(2)
        return articles

    def _parse_article(self, url: str) -> Optional[Dict]:
        soup = self._get(url, wait_css="h1, [class*='headline']")
        if not soup:
            return None

        headline = ""
        for sel in ["h1", "[class*='headline']", "[data-component='headline']"]:
            tag = soup.select_one(sel)
            if tag:
                headline = tag.get_text(strip=True)
                break
        if not headline:
            return None

        # Bloomberg paywalls full text; grab what's available
        paragraphs = [
            p.get_text(strip=True)
            for p in soup.select("p[class*='body'], .paywall-article p")
            if p.get_text(strip=True)
        ]
        full_text = " ".join(paragraphs)

        author_tag = soup.select_one("[class*='author'] a, [class*='byline']")
        author = author_tag.get_text(strip=True) if author_tag else "Bloomberg"

        time_tag = soup.select_one("time[datetime]")
        pub_date = time_tag["datetime"] if time_tag else datetime.now(timezone.utc).isoformat()

        return {
            "headline":     headline,
            "full_text":    full_text or "(Subscription required for full text)",
            "author":       author,
            "publish_date": pub_date,
            "source":       "Bloomberg",
            "source_url":   url,
            "category":     "Markets",
        }

    def run_and_save(self) -> int:
        articles = self.scrape()
        saved = 0
        for art in articles:
            aid = insert_article(art)
            if aid:
                saved += 1
        logger.info("Bloomberg: saved %d new articles", saved)
        return saved


# ── Generic JS site scraper ────────────────────────────────────────────────────

class GenericJSScraper(SeleniumScraper):
    """
    Configurable scraper for any JS-rendered news site.
    Pass CSS selectors for the site structure.
    """

    def __init__(self, source_name: str, index_urls: List[str],
                 headline_css: str, body_css: str,
                 author_css: str = "", time_css: str = "time[datetime]",
                 article_link_css: str = "a",
                 headless: bool = True):
        super().__init__(headless)
        self.source_name    = source_name
        self.index_urls     = index_urls
        self.headline_css   = headline_css
        self.body_css       = body_css
        self.author_css     = author_css
        self.time_css       = time_css
        self.article_link_css = article_link_css

    def scrape_and_save(self) -> int:
        saved = 0
        for idx_url in self.index_urls:
            soup = self._get(idx_url)
            if not soup:
                continue
            self._scroll_to_bottom()
            soup = BeautifulSoup(self.driver.page_source, "lxml")
            for link in soup.select(self.article_link_css)[:20]:
                href = link.get("href", "")
                if not href.startswith("http"):
                    domain = "/".join(idx_url.split("/")[:3])
                    href = f"{domain}{href}"
                if not href or article_exists(href):
                    continue
                art = self._parse_one(href)
                if art:
                    aid = insert_article(art)
                    if aid:
                        saved += 1
                time.sleep(2)
        return saved

    def _parse_one(self, url: str) -> Optional[Dict]:
        soup = self._get(url, wait_css=self.headline_css)
        if not soup:
            return None

        h_tag = soup.select_one(self.headline_css)
        headline = h_tag.get_text(strip=True) if h_tag else ""
        if not headline:
            return None

        body_tags = soup.select(self.body_css)
        full_text = " ".join(t.get_text(strip=True) for t in body_tags)

        author = self.source_name
        if self.author_css:
            a_tag = soup.select_one(self.author_css)
            if a_tag:
                author = a_tag.get_text(strip=True) or self.source_name

        time_tag = soup.select_one(self.time_css)
        pub_date = (
            time_tag.get("datetime", "") if time_tag
            else datetime.now(timezone.utc).isoformat()
        )

        return {
            "headline":     headline,
            "full_text":    full_text,
            "author":       author,
            "publish_date": pub_date,
            "source":       self.source_name,
            "source_url":   url,
            "category":     "Finance",
        }


# ── Convenience runner ─────────────────────────────────────────────────────────

def run_selenium_scrapers() -> Dict[str, int]:
    results = {}

    with BloombergScraper(headless=True) as scraper:
        results["Bloomberg"] = scraper.run_and_save()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    totals = run_selenium_scrapers()
    for src, count in totals.items():
        print(f"{src}: {count} new articles saved")
