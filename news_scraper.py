import time
from datetime import datetime
import logging
import sys
import argparse
import csv
import hashlib
import html
import os
import json
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    import feedparser
except ImportError:
    feedparser = SimpleNamespace(parse=None)

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    mysql = SimpleNamespace(connector=None)
    Error = Exception

try:
    import schedule
except ImportError:
    schedule = None

try:
    import requests
except ImportError:
    requests = None

# --- Configuration ---
# Database Credentials (Replace with your actual details)
DB_CONFIG = {
    "host": os.getenv("NEWS_DB_HOST", "YOUR_DATABASE_HOST"),
    "user": os.getenv("NEWS_DB_USER", "YOUR_DATABASE_USER"),
    "password": os.getenv("NEWS_DB_PASSWORD", "YOUR_DATABASE_PASSWORD"),
    "database": os.getenv("NEWS_DB_NAME", "YOUR_DATABASE_NAME"),
}

# RSS Feed URLs (Replace with the specific feeds you want)
# Find the correct URLs from publisher sites or search results.
# Axios might require a different approach or be omitted if no feed is found.
RSS_FEEDS = {
    "BBC News": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "Washington Post": "http://feeds.washingtonpost.com/rss/national?itid=lk_inline_manual_7",
    "Google News": "https://news.google.com/rss",
}

DEFAULT_FEED_TIMEOUT_SECONDS = 10
DEFAULT_FEED_RETRIES = 1

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

TRACKING_QUERY_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}

ARTICLE_FIELDS = [
    "id",
    "source",
    "url",
    "canonical_url",
    "headline",
    "author",
    "publish_date",
    "category",
    "summary",
]


def normalize_url(url):
    parsed = urlparse((url or "").strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_PARAMS
    ]
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            "",
            urlencode(sorted(query)),
            "",
        )
    )


def stable_article_id(url):
    canonical_url = normalize_url(url)
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


def load_feeds(path=None):
    if not path:
        return dict(RSS_FEEDS)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("feed config must be a JSON object of source name to feed URL")
    return data


def fetch_feed(feed_url, timeout=DEFAULT_FEED_TIMEOUT_SECONDS, retries=DEFAULT_FEED_RETRIES):
    if feedparser.parse is None:
        raise RuntimeError("feedparser is required to fetch RSS feeds")
    attempts = retries + 1
    last_error = None
    for _ in range(attempts):
        try:
            if requests is None:
                return feedparser.parse(feed_url)
            resp = requests.get(feed_url, timeout=timeout)
            resp.raise_for_status()
            return feedparser.parse(resp.content)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"failed to fetch feed after {attempts} attempt(s): {last_error}")


# --- Database Functions ---
def create_db_connection():
    """Creates and returns a MySQL database connection."""
    connection = None
    try:
        if mysql.connector is None:
            raise RuntimeError("mysql-connector-python is required for --store")
        connection = mysql.connector.connect(**DB_CONFIG)
        logging.info("MySQL Database connection successful")
    except Error as e:
        logging.error(f"Error connecting to MySQL Database: {e}")
    return connection


def format_feed_date(entry):
    """Attempts to parse and format date from feed entry."""
    dt = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))

    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        logging.warning(f"Could not parse date for entry: {entry.get('link')}")
        return None


def get_category(entry):
    """Extracts category/tags from feed entry if available."""
    tags = entry.get("tags") if hasattr(entry, "get") else getattr(entry, "tags", None)
    if tags:
        category = ", ".join(tag.get("term", "") for tag in tags if tag.get("term"))
        return category or None
    if hasattr(entry, "get"):
        return entry.get("category")
    return getattr(entry, "category", None)


def get_author(entry):
    """Extracts author from feed entry if available."""
    author = entry.get("author") if hasattr(entry, "get") else getattr(entry, "author", None)
    if author:
        return author
    authors = entry.get("authors") if hasattr(entry, "get") else getattr(entry, "authors", None)
    if authors:
        joined = ", ".join(author.get("name", "") for author in authors if author.get("name"))
        return joined or None
    return None


def article_from_entry(source_name, entry):
    url = entry.get("link")
    canonical_url = normalize_url(url)
    return {
        "id": stable_article_id(url),
        "source": source_name,
        "url": url,
        "canonical_url": canonical_url,
        "headline": entry.get("title"),
        "author": get_author(entry),
        "publish_date": format_feed_date(entry),
        "category": get_category(entry),
        "summary": html.unescape(entry.get("summary") or entry.get("description", "")),
    }


def export_articles(articles, export_format, output_path):
    if not export_format:
        return
    if export_format == "json":
        payload = json.dumps(articles, indent=2, ensure_ascii=False)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(payload + "\n")
        else:
            print(payload)
        return
    if export_format == "csv":
        if output_path:
            f = open(output_path, "w", newline="", encoding="utf-8")
            should_close = True
        else:
            f = sys.stdout
            should_close = False
        try:
            writer = csv.DictWriter(f, fieldnames=ARTICLE_FIELDS)
            writer.writeheader()
            writer.writerows(articles)
        finally:
            if should_close:
                f.close()
        return
    raise ValueError(f"Unsupported export format: {export_format}")


def insert_article(connection, article_data):
    """Inserts a single article from feed into the database, avoiding duplicates based on URL."""
    cursor = connection.cursor()
    check_query = "SELECT id FROM articles WHERE url = %s"
    cursor.execute(check_query, (article_data["url"],))
    result = cursor.fetchone()

    if result:
        # logging.info(f"Article already exists: {article_data['url']}") # Can be noisy
        return False  # Indicate article was not inserted

    insert_query = """
    INSERT INTO articles
    (source, url, headline, author, publish_date, category, summary)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    article_values = (
        article_data.get("source"),
        article_data.get("url"),
        article_data.get("headline"),
        article_data.get("author"),
        article_data.get("publish_date"),
        article_data.get("category"),
        article_data.get("summary"),
        # Note: full_text is not populated here, requires separate scraping step if needed
    )

    try:
        cursor.execute(insert_query, article_values)
        connection.commit()
        logging.info(
            f"Article inserted: {article_data['headline'][:50]}... ({article_data['source']})"
        )
        return True  # Indicate successful insertion
    except Error as e:
        logging.error(f"Failed to insert article {article_data.get('url')}: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()


# --- Main Job Function ---


def fetch_and_store_feeds(
    store: bool,
    export_format=None,
    output_path=None,
    feeds=None,
    timeout=DEFAULT_FEED_TIMEOUT_SECONDS,
    retries=DEFAULT_FEED_RETRIES,
    return_report=False,
):
    """Fetch articles from RSS feeds, optionally storing or exporting them.

    Args:
        store: if true, store data into database.
        export_format: optional "json" or "csv" output format.
        output_path: optional file path for exported articles.
        feeds: optional mapping of source name to feed URL.
        timeout: per-feed HTTP timeout in seconds.
        retries: retry count after the first failed attempt.
    """
    logging.info("Starting RSS feed fetch job...")
    connection = None
    if store:
        connection = create_db_connection()
        if not connection:
            logging.error("Could not establish database connection. Aborting job.")
            return

    total_inserted = 0
    total_processed = 0
    articles = []
    failures = []
    seen_article_ids = set()
    feed_map = feeds or RSS_FEEDS

    for source_name, feed_url in feed_map.items():
        logging.info(f"Fetching feed for: {source_name} from {feed_url}")
        try:
            feed_data = fetch_feed(feed_url, timeout=timeout, retries=retries)

            if feed_data.bozo:
                logging.warning(
                    f"""Feed for {source_name} might be ill-formed. Bozo 
                    reason: {feed_data.get('bozo_exception', 'Unknown')}"""
                )

            processed_count = 0
            inserted_count = 0
            # Iterate through entries (articles) in the feed
            for entry in feed_data.entries:
                processed_count += 1
                total_processed += 1

                article = article_from_entry(source_name, entry)

                # Basic validation
                if not article["url"] or not article["headline"]:
                    logging.warning(
                        f"Skipping entry with missing URL or headline from {source_name}"
                    )
                    continue

                if article["id"] in seen_article_ids:
                    continue
                seen_article_ids.add(article["id"])
                articles.append(article)

                if not store:
                    if not export_format:
                        print(article)
                    inserted_count += 1
                    total_inserted += 1
                    continue

                if insert_article(connection, article):
                    inserted_count += 1
                    total_inserted += 1

            logging.info(
                f"""Finished processing {source_name}. Processed entries: 
                {processed_count}, New entries inserted: {inserted_count}"""
            )

        except Exception as e:
            failures.append({"source": source_name, "url": feed_url, "error": str(e)})
            logging.error(
                f"Error processing feed {source_name} ({feed_url}): {e}", 
                exc_info=True
            )

    if store and connection and connection.is_connected():
        connection.close()
        logging.info("MySQL connection closed.")

    export_articles(articles, export_format, output_path)

    logging.info(
        f"""RSS feed fetch job finished. Total entries processed: 
        {total_processed}, Total new articles inserted: {total_inserted}"""
    )
    if failures:
        logging.warning("Partial feed failures: %s", failures)
    if return_report:
        return {"articles": articles, "failures": failures}
    return articles


# --- Main iteration function ---
def main(args):
    # Optional: Run once immediately on start for testing
    if args.test:
        logging.info("Running as a test...")
        feeds = load_feeds(args.feeds)
        fetch_and_store_feeds(args.store, args.export, args.output, feeds=feeds, timeout=args.feed_timeout, retries=args.feed_retries)
        return 0
    if schedule is None:
        raise RuntimeError("schedule is required for scheduled mode")

    # Schedule the job to run once every day at a specific time (e.g., 4:00 AM)
    schedule.every().day.at("04:00").do(
        fetch_and_store_feeds,
        store=args.store,
        export_format=args.export,
        output_path=args.output,
        feeds=load_feeds(args.feeds),
        timeout=args.feed_timeout,
        retries=args.feed_retries,
    )

    logging.info("RSS Collector starting. Waiting for scheduled job...")
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every 60 seconds if a scheduled job is due


if __name__ == "__main__":
    # 1. Set up argument parsing (optional, but common)
    parser = argparse.ArgumentParser(description="News Scraper")
    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help="If true, will run scraper once and then exit",
    )
    parser.add_argument(
        "-s",
        "--store",
        action="store_true",
        help="""If true, will store data into database. If not, 
        will just print out in console unless export is enabled.""",
    )
    parser.add_argument(
        "--export",
        choices=("json", "csv"),
        help="Export fetched articles without requiring MySQL storage.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output path for --export json/csv.",
    )
    parser.add_argument(
        "--feeds",
        help="Path to JSON feed config: {\"Source\": \"https://feed\"}.",
    )
    parser.add_argument(
        "--feed-timeout",
        type=float,
        default=DEFAULT_FEED_TIMEOUT_SECONDS,
        help="Per-feed HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--feed-retries",
        type=int,
        default=DEFAULT_FEED_RETRIES,
        help="Retries per feed after the first failed attempt.",
    )

    # 2. Parse the command-line arguments
    # If parsing fails, argparse automatically exits with an error message.
    parsed_args = parser.parse_args()

    # 3. Call the main function and exit with its status code
    # This makes the script's exit code reflect the success/failure within main()
    exit_code = main(parsed_args)
    sys.exit(exit_code)
