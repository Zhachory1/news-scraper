import csv
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import news_scraper


class FeedEntry(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class NewsScraperTests(unittest.TestCase):
    def entry(self, **overrides):
        base = {
            "link": "https://Example.com/story?utm_source=rss&id=42#section",
            "title": "A headline",
            "summary": "A &amp; B",
            "published_parsed": time.strptime("2026-06-19 12:30:00", "%Y-%m-%d %H:%M:%S"),
            "tags": [{"term": "Politics"}, {"term": "World"}],
            "authors": [{"name": "Reporter One"}, {"name": "Reporter Two"}],
        }
        base.update(overrides)
        return FeedEntry(base)

    def test_article_from_entry_uses_canonical_schema(self):
        article = news_scraper.article_from_entry("Test Source", self.entry())

        self.assertEqual(set(article), set(news_scraper.ARTICLE_FIELDS))
        self.assertEqual(article["source"], "Test Source")
        self.assertEqual(article["canonical_url"], "https://example.com/story?id=42")
        self.assertEqual(article["summary"], "A & B")
        self.assertEqual(article["category"], "Politics, World")
        self.assertEqual(article["author"], "Reporter One, Reporter Two")
        self.assertRegex(article["id"], r"^[0-9a-f]{16}$")

    def test_stable_id_ignores_tracking_params_and_fragments(self):
        first = news_scraper.stable_article_id("https://example.com/story?id=42&utm_medium=social#x")
        second = news_scraper.stable_article_id("https://EXAMPLE.com/story/?utm_source=rss&id=42")

        self.assertEqual(first, second)

    def test_fetch_deduplicates_by_stable_id(self):
        feed = FeedEntry(
            {
                "bozo": False,
                "entries": [
                    self.entry(link="https://example.com/story?id=42&utm_source=rss"),
                    self.entry(link="https://example.com/story/?id=42#duplicate"),
                ],
            }
        )

        with TemporaryDirectory() as tmp, patch.object(
            news_scraper.feedparser, "parse", return_value=feed
        ), patch.dict(news_scraper.RSS_FEEDS, {"Test": "https://feed.example/rss"}, clear=True):
            articles = news_scraper.fetch_and_store_feeds(
                store=False,
                export_format="json",
                output_path=Path(tmp) / "articles.json",
            )

        self.assertEqual(len(articles), 1)

    def test_export_articles_writes_json_and_csv(self):
        articles = [news_scraper.article_from_entry("Test", self.entry())]
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "articles.json"
            csv_path = Path(tmp) / "articles.csv"

            news_scraper.export_articles(articles, "json", json_path)
            news_scraper.export_articles(articles, "csv", csv_path)

            self.assertEqual(json.loads(json_path.read_text())[0]["headline"], "A headline")
            with csv_path.open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["headline"], "A headline")


if __name__ == "__main__":
    unittest.main()
