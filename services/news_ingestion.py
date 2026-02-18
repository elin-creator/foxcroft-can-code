"""
News and media ingestion service.
Uses free RSS feeds and publicly accessible sources.
Focused on RECENCY — pulls only recent articles (7-14 days by default).
"""

import httpx
import feedparser
import re
import json
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from typing import Optional
from models.database import get_db

# Google News RSS (free, no API key)
# when= parameter: 1d, 7d, 14d, 1m
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en&when={when}"

# Reliable free RSS feeds (verified working as of 2025)
NEWS_FEEDS = {
    "sec_press": "https://www.sec.gov/news/pressreleases.rss",
    "sec_litigation": "https://www.sec.gov/rss/litigation/litreleases.xml",
    "pr_newswire_business": "https://www.prnewswire.com/rss/news-releases-list.rss",
    "businesswire": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFtTXA==",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
}


async def fetch_rss_feed(url: str, timeout: int = 20) -> list[dict]:
    """Fetch and parse an RSS feed."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; PNGSMonitor/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            })
            if resp.status_code != 200:
                return []
        except Exception:
            return []

    feed = feedparser.parse(resp.text)
    articles = []
    for entry in feed.entries[:30]:
        pub_date = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_date = datetime(*entry.published_parsed[:6]).isoformat()
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            pub_date = datetime(*entry.updated_parsed[:6]).isoformat()

        # Clean HTML from summary
        summary = entry.get("summary", "")
        summary = re.sub(r'<[^>]+>', '', summary).strip()

        articles.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "summary": summary[:3000],
            "published_date": pub_date,
            "source": feed.feed.get("title", "Unknown"),
        })

    return articles


async def search_google_news(query: str, days_back: int = 7) -> list[dict]:
    """
    Search Google News RSS for a specific query.
    days_back controls recency: 1, 7, 14, or 30 days.
    """
    # Map to Google News 'when' parameter
    if days_back <= 1:
        when = "1d"
    elif days_back <= 7:
        when = "7d"
    elif days_back <= 14:
        when = "14d"
    else:
        when = "1m"

    encoded_query = quote_plus(query)
    url = GOOGLE_NEWS_RSS.format(query=encoded_query, when=when)

    articles = await fetch_rss_feed(url)

    # Double-check recency: filter out articles older than requested window
    cutoff = datetime.now() - timedelta(days=days_back + 1)
    recent = []
    for a in articles:
        if a["published_date"]:
            try:
                pub = datetime.fromisoformat(a["published_date"].replace("Z", "+00:00").replace("+00:00", ""))
                if pub >= cutoff:
                    recent.append(a)
                    continue
            except (ValueError, TypeError):
                pass
        # If we can't parse the date, include it (likely recent if in the RSS)
        recent.append(a)

    return recent


async def fetch_article_text(url: str, max_chars: int = 15000) -> str:
    """Attempt to fetch article text. Basic extraction with better heuristics."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; PNGSMonitor/1.0)"
            })
            if resp.status_code != 200:
                return ""

            text = resp.text

            # Try to extract main content
            for tag in ['<article', '<main', '<div class="article', '<div class="content',
                        '<div class="story', '<div class="post', '<div class="entry']:
                start = text.find(tag)
                if start >= 0:
                    # Find matching close tag
                    close_tag = '</article>' if 'article' in tag else '</main>' if 'main' in tag else '</div>'
                    end = text.find(close_tag, start + 100)
                    if end > start:
                        text = text[start:end]
                        break

            # Strip scripts, styles, nav elements
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL)
            text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL)
            text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
    except Exception:
        return ""


async def ingest_news(company_id: int, ticker: str, company_name: str, days_back: int = 7) -> dict:
    """
    Ingest recent news articles about a company.
    Default: last 7 days only for timely analysis.
    """
    db = await get_db()
    try:
        all_articles = []

        # Search Google News with multiple query variations (recent only)
        queries = [
            f'"{company_name}"',
            f'{ticker} stock',
            f'"{company_name}" CEO OR board OR earnings',
        ]
        for query in queries:
            try:
                articles = await search_google_news(query, days_back=days_back)
                all_articles.extend(articles)
            except Exception:
                continue

        # Scan targeted RSS feeds for company mentions
        for feed_name, feed_url in NEWS_FEEDS.items():
            try:
                articles = await fetch_rss_feed(feed_url)
                for a in articles:
                    text = f"{a['title']} {a['summary']}".lower()
                    if ticker.lower() in text or company_name.lower() in text:
                        a["source"] = feed_name
                        all_articles.append(a)
            except Exception:
                continue

        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for a in all_articles:
            url = a.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(a)

        # Filter for recency one more time
        cutoff = datetime.now() - timedelta(days=days_back + 1)
        ingested = 0
        skipped_old = 0

        for article in unique_articles:
            # Skip articles that are clearly too old
            if article.get("published_date"):
                try:
                    pub = datetime.fromisoformat(article["published_date"].replace("Z", "").split("+")[0])
                    if pub < cutoff:
                        skipped_old += 1
                        continue
                except (ValueError, TypeError):
                    pass

            # Check if already exists
            existing = await db.execute(
                "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
                (company_id, article["url"])
            )
            if await existing.fetchone():
                continue

            # Use summary as content; fetch full text if summary is too short
            content = article["summary"]
            if len(content) < 200:
                full_text = await fetch_article_text(article["url"])
                if full_text:
                    content = full_text

            if content and len(content) > 50:
                await db.execute(
                    """INSERT INTO documents (company_id, source_type, source_url, title, content,
                       published_date, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        company_id,
                        "news",
                        article["url"],
                        article["title"],
                        content,
                        article.get("published_date"),
                        json.dumps({"source_feed": article.get("source", ""), "ingested_for_period": f"last_{days_back}d"}),
                    )
                )
                ingested += 1

        await db.commit()
        return {
            "status": "success",
            "documents_ingested": ingested,
            "total_found": len(unique_articles),
            "skipped_old": skipped_old,
            "window": f"last {days_back} days",
        }

    finally:
        await db.close()


async def ingest_press_releases(company_id: int, ticker: str, company_name: str, days_back: int = 14) -> dict:
    """Ingest recent press releases. Default: last 14 days."""
    db = await get_db()
    try:
        articles = await search_google_news(
            f'"{company_name}" (press release OR announcement OR "announces")',
            days_back=days_back
        )

        ingested = 0
        for article in articles:
            existing = await db.execute(
                "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
                (company_id, article["url"])
            )
            if await existing.fetchone():
                continue

            content = article["summary"]
            if len(content) < 200:
                full_text = await fetch_article_text(article["url"])
                if full_text:
                    content = full_text

            if content and len(content) > 50:
                await db.execute(
                    """INSERT INTO documents (company_id, source_type, source_url, title, content,
                       published_date, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        company_id,
                        "press_release",
                        article["url"],
                        article["title"],
                        content,
                        article.get("published_date"),
                        json.dumps({"source_feed": article.get("source", "")}),
                    )
                )
                ingested += 1

        await db.commit()
        return {"status": "success", "documents_ingested": ingested, "window": f"last {days_back} days"}
    finally:
        await db.close()
