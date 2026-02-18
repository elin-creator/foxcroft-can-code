"""
News and media ingestion service.
Uses free RSS feeds and publicly accessible sources.
"""

import httpx
import feedparser
import re
import json
from datetime import datetime, timedelta
from typing import Optional
from models.database import get_db

# Free RSS sources for financial/business news
NEWS_FEEDS = {
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "reuters_companies": "https://feeds.reuters.com/reuters/companyNews",
    "sec_press": "https://www.sec.gov/news/pressreleases.rss",
    "pr_newswire": "https://www.prnewswire.com/rss/financial-services-latest-news.rss",
    "businesswire": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFtTXA==",
}

# Google News RSS (free, no API key)
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


async def fetch_rss_feed(url: str, timeout: int = 20) -> list[dict]:
    """Fetch and parse an RSS feed."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": "PNGSMonitor/1.0"})
            if resp.status_code != 200:
                return []
        except Exception:
            return []

    feed = feedparser.parse(resp.text)
    articles = []
    for entry in feed.entries[:20]:
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
            "summary": summary[:2000],
            "published_date": pub_date,
            "source": feed.feed.get("title", "Unknown"),
        })

    return articles


async def search_google_news(query: str, days_back: int = 30) -> list[dict]:
    """Search Google News RSS for a specific query."""
    # Add time filter to query
    url = GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+"))
    if days_back:
        url += f"&after:{(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')}"

    return await fetch_rss_feed(url)


async def fetch_article_text(url: str, max_chars: int = 15000) -> str:
    """Attempt to fetch article text. Basic extraction."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "PNGSMonitor/1.0"})
            if resp.status_code != 200:
                return ""

            text = resp.text
            # Try to extract main content between common article tags
            # This is a simple heuristic; production would use readability/newspaper3k
            for tag in ['<article', '<main', '<div class="article', '<div class="content']:
                start = text.find(tag)
                if start >= 0:
                    end = text.find('</article>' if 'article' in tag else '</main>', start)
                    if end > start:
                        text = text[start:end]
                        break

            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
    except Exception:
        return ""


async def ingest_news(company_id: int, ticker: str, company_name: str) -> dict:
    """Ingest news articles about a company from multiple sources."""
    db = await get_db()
    try:
        all_articles = []

        # Search Google News for the company
        for query in [f'"{company_name}" stock', f'{ticker} company', f'"{company_name}" CEO']:
            articles = await search_google_news(query, days_back=60)
            all_articles.extend(articles)

        # Also scan general business feeds for mentions
        for feed_name, feed_url in NEWS_FEEDS.items():
            try:
                articles = await fetch_rss_feed(feed_url)
                # Filter for company mentions
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
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                unique_articles.append(a)

        ingested = 0
        for article in unique_articles:
            # Check if already exists
            existing = await db.execute(
                "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
                (company_id, article["url"])
            )
            if await existing.fetchone():
                continue

            # Use summary as content; optionally fetch full text
            content = article["summary"]
            if len(content) < 200:
                full_text = await fetch_article_text(article["url"])
                if full_text:
                    content = full_text

            if content:
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
                        json.dumps({"source_feed": article.get("source", "")}),
                    )
                )
                ingested += 1

        await db.commit()
        return {"status": "success", "documents_ingested": ingested, "total_found": len(unique_articles)}

    finally:
        await db.close()


async def ingest_press_releases(company_id: int, ticker: str, company_name: str) -> dict:
    """Ingest press releases specifically."""
    db = await get_db()
    try:
        articles = await search_google_news(f'"{company_name}" press release OR announcement', days_back=90)

        ingested = 0
        for article in articles:
            existing = await db.execute(
                "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
                (company_id, article["url"])
            )
            if await existing.fetchone():
                continue

            content = article["summary"]
            if content:
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
        return {"status": "success", "documents_ingested": ingested}
    finally:
        await db.close()
