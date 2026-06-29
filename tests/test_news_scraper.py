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

    def test_load_feeds_from_json(self):
        with TemporaryDirectory() as tmp:
            feeds = Path(tmp) / "feeds.json"
            feeds.write_text(json.dumps({"Example": "https://example.com/rss"}))

            self.assertEqual(news_scraper.load_feeds(feeds), {"Example": "https://example.com/rss"})

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
            news_scraper, "fetch_feed", return_value=feed
        ), patch.dict(news_scraper.RSS_FEEDS, {"Test": "https://feed.example/rss"}, clear=True):
            articles = news_scraper.fetch_and_store_feeds(
                store=False,
                export_format="json",
                output_path=Path(tmp) / "articles.json",
            )

        self.assertEqual(len(articles), 1)

    def test_fetch_reports_partial_feed_failures(self):
        good_feed = FeedEntry({"bozo": False, "entries": [self.entry()]})

        def fake_fetch(url, timeout=10, retries=1):
            if "bad" in url:
                raise RuntimeError("timeout")
            return good_feed

        with patch.object(news_scraper, "fetch_feed", side_effect=fake_fetch):
            report = news_scraper.fetch_and_store_feeds(
                store=False,
                feeds={"Good": "https://feed.example/rss", "Bad": "https://bad.example/rss"},
                return_report=True,
            )

        self.assertEqual(len(report["articles"]), 1)
        self.assertEqual(report["failures"][0]["source"], "Bad")

    def test_export_articles_writes_json_csv_and_markdown(self):
        articles = [news_scraper.article_from_entry("Test", self.entry())]
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "articles.json"
            csv_path = Path(tmp) / "articles.csv"
            markdown_path = Path(tmp) / "digest.md"

            news_scraper.export_articles(articles, "json", json_path)
            news_scraper.export_articles(articles, "csv", csv_path)
            news_scraper.export_articles(articles, "markdown", markdown_path)

            self.assertEqual(json.loads(json_path.read_text())[0]["headline"], "A headline")
            with csv_path.open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["headline"], "A headline")
            digest = markdown_path.read_text()
            self.assertIn("# News Digest", digest)
            self.assertIn("[A headline](https://example.com/story?id=42)", digest)
            self.assertIn("Test · 2026-06-19 12:30:00 · Politics, World", digest)
            self.assertIn("A & B", digest)


if __name__ == "__main__":
    unittest.main()
