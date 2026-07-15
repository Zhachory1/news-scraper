# News Scraper

This is my own personal web scraper for a list of news websites that I like to follow. The scraper will extract different parts of articles and store them in a SQL database.

My intention is to do some analysis and possibly cluster these articles to identify trending stories and such. 

First step first, let's make a News Webscraper

Working from this set of rss feeds: https://github.com/plenaryapp/awesome-rss-feeds?tab=readme-ov-file#News

## Running

To start the schedule, run the following command

```
source start_job.sh
```

If you just want to test things, you can just add the test flag

```
source start_job.sh -t
```

Export fetched articles without writing to MySQL:

```
python news_scraper.py -t --export json --output articles.json
python news_scraper.py -t --export csv --output articles.csv
python news_scraper.py -t --export markdown --output digest.md
```

Use a feed config outside source code:

```json
{
  "BBC News": "http://feeds.bbci.co.uk/news/world/rss.xml",
  "Google News": "https://news.google.com/rss"
}
```

```bash
python news_scraper.py -t --feeds feeds.json --feed-timeout 5 --feed-retries 2
```

No-store mode prints or exports articles without MySQL:

```bash
python news_scraper.py -t --export json --output articles.json
```

DB-backed mode requires environment variables from `.env.example`:

```bash
export NEWS_DB_HOST=localhost
export NEWS_DB_USER=news_scraper
export NEWS_DB_PASSWORD=change-me
export NEWS_DB_NAME=news_articles
python news_scraper.py -t --store
```

Each exported article uses the canonical schema:

- `id` — stable SHA-256-derived ID from canonical URL
- `source`
- `url`
- `canonical_url`
- `headline`
- `author`
- `publish_date`
- `category`
- `summary`

## Tests

```
python -m unittest discover -s tests
```
