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
