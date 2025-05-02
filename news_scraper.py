import feedparser
import mysql.connector
from mysql.connector import Error
import schedule
import time
from datetime import datetime
import logging
import sys
import argparse # Often used for command-line arguments
import html # To potentially decode HTML entities in summaries

# --- Configuration ---
# Database Credentials (Replace with your actual details)
DB_CONFIG = {
    'host': 'YOUR_DATABASE_HOST',        # e.g., 'localhost'
    'user': 'YOUR_DATABASE_USER',        # e.g., 'root'
    'password': 'YOUR_DATABASE_PASSWORD',
    'database': 'YOUR_DATABASE_NAME'     # e.g., 'news_articles'
}

# RSS Feed URLs (Replace with the specific feeds you want)
# Find the correct URLs from publisher sites or search results.
# Axios might require a different approach or be omitted if no feed is found.
RSS_FEEDS = {
    'BBC News': 'http://feeds.bbci.co.uk/news/world/rss.xml',
    'Reuters': 'http://feeds.reuters.com/reuters/topNews',
    'New York Times': 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml',
    'Washington Post': 'http://feeds.washingtonpost.com/rss/national?itid=lk_inline_manual_7', # Example: National
    'The Atlantic': 'https://www.theatlantic.com/feed/channel/news/', # Example: News section feed (verify)
    # 'Axios': 'URL_IF_FOUND' # Add Axios feed URL if you find a reliable one
}

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Database Functions ---

def create_db_connection():
    """Creates and returns a MySQL database connection."""
    connection = None
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        logging.info("MySQL Database connection successful")
    except Error as e:
        logging.error(f"Error connecting to MySQL Database: {e}")
    return connection

def format_feed_date(entry):
    """Attempts to parse and format date from feed entry."""
    dt = None
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))

    if dt:
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        logging.warning(f"Could not parse date for entry: {entry.get('link')}")
        return None

def get_category(entry):
    """Extracts category/tags from feed entry if available."""
    if hasattr(entry, 'tags'):
        # entry.tags is often a list of dicts like [{'term': 'Politics', 'scheme': None, 'label': None}, ...]
        return ', '.join(tag.get('term', '') for tag in entry.tags if tag.get('term'))
    elif hasattr(entry, 'category'):
         return entry.category # Sometimes it's a simple string attribute
    return None

def get_author(entry):
    """Extracts author from feed entry if available."""
    if hasattr(entry, 'author'):
        return entry.author
    elif hasattr(entry, 'authors'):
         # entry.authors might be a list of dicts
         return ', '.join(author.get('name', '') for author in entry.authors if author.get('name'))
    return None

def insert_article(connection, article_data):
    """Inserts a single article from feed into the database, avoiding duplicates based on URL."""
    cursor = connection.cursor()
    check_query = "SELECT id FROM articles WHERE url = %s"
    cursor.execute(check_query, (article_data['url'],))
    result = cursor.fetchone()

    if result:
        # logging.info(f"Article already exists: {article_data['url']}") # Can be noisy
        return False # Indicate article was not inserted

    insert_query = """
    INSERT INTO articles
    (source, url, headline, author, publish_date, category, summary)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    article_values = (
        article_data.get('source'),
        article_data.get('url'),
        article_data.get('headline'),
        article_data.get('author'),
        article_data.get('publish_date'),
        article_data.get('category'),
        article_data.get('summary')
        # Note: full_text is not populated here, requires separate scraping step if needed
    )

    try:
        cursor.execute(insert_query, article_values)
        connection.commit()
        logging.info(f"Article inserted: {article_data['headline'][:50]}... ({article_data['source']})")
        return True # Indicate successful insertion
    except Error as e:
        logging.error(f"Failed to insert article {article_data.get('url')}: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()

# --- Main Job Function ---

def fetch_and_store_feeds():
    """Fetches articles from RSS feeds and stores them in the database."""
    logging.info("Starting RSS feed fetch job...")
    connection = create_db_connection()
    if not connection:
        logging.error("Could not establish database connection. Aborting job.")
        return

    total_inserted = 0
    total_processed = 0

    for source_name, feed_url in RSS_FEEDS.items():
        logging.info(f"Fetching feed for: {source_name} from {feed_url}")
        try:
            # Parse the feed
            feed_data = feedparser.parse(feed_url)

            if feed_data.bozo:
                 logging.warning(f"Feed for {source_name} might be ill-formed. Bozo reason: {feed_data.get('bozo_exception', 'Unknown')}")

            processed_count = 0
            inserted_count = 0
            # Iterate through entries (articles) in the feed
            for entry in feed_data.entries:
                processed_count += 1
                total_processed += 1

                # Extract data using feedparser attributes
                article = {
                    'source': source_name,
                    'url': entry.get('link'),
                    'headline': entry.get('title'),
                    'author': get_author(entry),
                    'publish_date': format_feed_date(entry),
                    'category': get_category(entry),
                    # Get summary or description, decode HTML entities
                    'summary': html.unescape(entry.get('summary') or entry.get('description', ''))
                }

                # Basic validation
                if not article['url'] or not article['headline']:
                    logging.warning(f"Skipping entry with missing URL or headline from {source_name}")
                    continue

                # Insert into database
                if insert_article(connection, article):
                    inserted_count += 1
                    total_inserted += 1

            logging.info(f"Finished processing {source_name}. Processed entries: {processed_count}, New entries inserted: {inserted_count}")

        except Exception as e:
            logging.error(f"Error processing feed {source_name} ({feed_url}): {e}", exc_info=True)

    if connection and connection.is_connected():
        connection.close()
        logging.info("MySQL connection closed.")

    logging.info(f"RSS feed fetch job finished. Total entries processed: {total_processed}, Total new articles inserted: {total_inserted}")


# --- Scheduling ---



def main(args):
    # Optional: Run once immediately on start for testing
    if args.test:  
        logging.info("Running as a test...")
        fetch_and_store_feeds()
        return 0
    # Schedule the job to run once every day at a specific time (e.g., 4:00 AM)
    schedule.every().day.at("04:00").do(fetch_and_store_feeds)

    logging.info("RSS Collector starting. Waiting for scheduled job...")
    while True:
        schedule.run_pending()
        time.sleep(60) # Check every 60 seconds if a scheduled job is due

if __name__ == "__main__":
    # 1. Set up argument parsing (optional, but common)
    parser = argparse.ArgumentParser(description="News Scraper")
    parser.add_argument('-t', '--test',
                    action='store_true', help="If set, will run scraper once and then exit")
    parser.add_argument('')
    # Add other arguments as needed

    # 2. Parse the command-line arguments
    # If parsing fails, argparse automatically exits with an error message.
    parsed_args = parser.parse_args()

    # 3. Call the main function and exit with its status code
    # This makes the script's exit code reflect the success/failure within main()
    exit_code = main(parsed_args)
    sys.exit(exit_code)