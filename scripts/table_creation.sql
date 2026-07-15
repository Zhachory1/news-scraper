-- First, create a database if you don't have one already (optional)
-- CREATE DATABASE news_articles;

-- Use the database
-- USE news_articles;

-- Create the table to store article information
CREATE TABLE IF NOT EXISTS articles (
    id VARCHAR(16) PRIMARY KEY,
    source VARCHAR(50) NOT NULL,         -- e.g., 'BBC News', 'Reuters'
    url VARCHAR(1024) NOT NULL,
    canonical_url VARCHAR(1024) NOT NULL UNIQUE,
    headline TEXT NOT NULL,              -- Article title
    author VARCHAR(255),                 -- Author name(s)
    publish_date DATETIME,               -- Publication date/time
    category VARCHAR(100),               -- Article category/section
    summary TEXT,                        -- Feed summary/description
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- When the article was scraped
);

-- Add an index for faster canonical URL lookups
CREATE INDEX idx_canonical_url ON articles (canonical_url(255));
