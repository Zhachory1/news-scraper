-- First, create a database if you don't have one already (optional)
-- CREATE DATABASE news_articles;

-- Use the database
-- USE news_articles;

-- Create the table to store article information
CREATE TABLE IF NOT EXISTS articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(50) NOT NULL,         -- e.g., 'BBC News', 'Reuters'
    url VARCHAR(1024) NOT NULL UNIQUE,   -- Article URL (Unique to prevent duplicates)
    headline TEXT NOT NULL,              -- Article title
    author VARCHAR(255),                 -- Author name(s)
    publish_date DATETIME,               -- Publication date/time
    category VARCHAR(100),               -- Article category/section
    full_text LONGTEXT,                  -- Full text content (can be very long)
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- When the article was scraped
);

-- Add an index for faster URL lookups
CREATE INDEX idx_url ON articles (url(255)); -- Index part of the URL for efficiency