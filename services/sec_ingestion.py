"""
SEC EDGAR ingestion service.
Uses the free SEC EDGAR FULL-TEXT search and filing APIs.
Requires a User-Agent header per SEC policy.
"""

import httpx
import json
import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from models.database import get_db

SEC_BASE = "https://efts.sec.gov/LATEST"
SEC_FILINGS = "https://data.sec.gov"
# SEC requires: "Sample Company Name AdminContact@<sample company domain>.com"
# Users should update this with their real email
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "SignalMonitor/1.0 (admin@signalmonitor.app)"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

# Filing types we care about
RELEVANT_FILINGS = ["10-K", "10-Q", "8-K", "DEF 14A", "DEFA14A", "SC 13D", "SC 13D/A"]


async def lookup_cik(ticker: str) -> Optional[str]:
    """Look up CIK number from ticker via SEC company tickers JSON."""
    headers = {**HEADERS, "Host": "data.sec.gov"}
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(f"https://www.sec.gov/files/company_tickers.json")
            if resp.status_code == 200:
                data = resp.json()
                for entry in data.values():
                    if entry.get("ticker", "").upper() == ticker.upper():
                        return str(entry["cik_str"]).zfill(10)
        except Exception as e:
            print(f"[SEC] CIK lookup error for {ticker}: {e}", flush=True)
    return None


async def fetch_recent_filings(cik: str, filing_types: list[str] = None, count: int = 20) -> list[dict]:
    """Fetch recent filings for a CIK from EDGAR."""
    if filing_types is None:
        filing_types = RELEVANT_FILINGS

    cik_padded = cik.zfill(10)
    url = f"{SEC_FILINGS}/submissions/CIK{cik_padded}.json"
    headers = {**HEADERS, "Host": "data.sec.gov"}

    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
        try:
            # Rate limit: SEC allows 10 req/sec
            await asyncio.sleep(0.15)
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[SEC] Filings fetch failed: HTTP {resp.status_code} for CIK {cik_padded}", flush=True)
                return []
        except Exception as e:
            print(f"[SEC] Filings fetch error: {e}", flush=True)
            return []

        data = resp.json()
        filings = []
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        for i in range(min(len(forms), count * 3)):
            if forms[i] in filing_types:
                acc_clean = accessions[i].replace("-", "")
                doc_url = f"{SEC_FILINGS}/Archives/edgar/data/{cik_padded}/{acc_clean}/{primary_docs[i]}"
                filings.append({
                    "form_type": forms[i],
                    "filing_date": dates[i],
                    "accession": accessions[i],
                    "document_url": doc_url,
                    "description": descriptions[i] if i < len(descriptions) else "",
                })
                if len(filings) >= count:
                    break

        return filings


async def fetch_filing_text(url: str, max_chars: int = 50000) -> str:
    """Fetch the text content of a filing. Strips HTML tags for processing."""
    # Determine correct Host header based on URL
    if "data.sec.gov" in url:
        host = "data.sec.gov"
    elif "sec.gov" in url:
        host = "www.sec.gov"
    else:
        host = ""
    
    headers = {**HEADERS}
    if host:
        headers["Host"] = host

    async with httpx.AsyncClient(headers=headers, timeout=60, follow_redirects=True) as client:
        try:
            await asyncio.sleep(0.15)  # Rate limit
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[SEC] Filing text fetch failed: HTTP {resp.status_code} for {url[:80]}", flush=True)
                return ""
            text = resp.text
            # Strip HTML tags for plain text extraction
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
        except Exception as e:
            print(f"[SEC] Filing text error: {e}", flush=True)
            return ""


async def search_edgar_fulltext(query: str, date_range: str = None, forms: str = None, count: int = 10) -> list[dict]:
    """Use EDGAR full-text search (EFTS) to find filings matching a query."""
    params = {"q": query, "dateRange": "custom", "startdt": "", "enddt": "", "forms": forms or ""}

    if date_range:
        # e.g. "2024-01-01,2025-01-01"
        parts = date_range.split(",")
        params["startdt"] = parts[0]
        params["enddt"] = parts[1] if len(parts) > 1 else ""

    # Default to last 12 months
    if not params["startdt"]:
        params["startdt"] = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        params["enddt"] = datetime.now().strftime("%Y-%m-%d")

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        resp = await client.get(f"{SEC_BASE}/search-index", params=params)
        if resp.status_code != 200:
            return []

        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        results = []
        for hit in hits[:count]:
            src = hit.get("_source", {})
            results.append({
                "entity_name": src.get("entity_name", ""),
                "file_date": src.get("file_date", ""),
                "form_type": src.get("form_type", ""),
                "file_num": src.get("file_num", ""),
                "period_of_report": src.get("period_of_report", ""),
                "url": f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id', '')}/{src.get('file_num', '')}",
            })
        return results


async def ingest_sec_filings(company_id: int, ticker: str, cik: str = None) -> dict:
    """Main ingestion function: fetch and store recent SEC filings for a company.
    Focuses on most recent filings (last 90 days prioritized)."""
    db = await get_db()
    try:
        if not cik:
            cik = await lookup_cik(ticker)
            if not cik:
                return {"status": "error", "message": f"Could not find CIK for {ticker}"}

            # Store CIK
            await db.execute("UPDATE companies SET cik = ? WHERE id = ?", (cik, company_id))
            await db.commit()

        filings = await fetch_recent_filings(cik, count=15)

        # Sort by filing date descending to prioritize most recent
        filings.sort(key=lambda f: f.get("filing_date", ""), reverse=True)

        ingested = 0
        cutoff_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        for f in filings:
            # Skip filings older than 6 months
            if f.get("filing_date", "") < cutoff_date:
                continue

            # Check if already ingested
            existing = await db.execute(
                "SELECT id FROM documents WHERE company_id = ? AND source_url = ?",
                (company_id, f["document_url"])
            )
            if await existing.fetchone():
                continue

            # Fetch text content (truncated for storage/processing)
            content = await fetch_filing_text(f["document_url"], max_chars=40000)

            if content:
                await db.execute(
                    """INSERT INTO documents (company_id, source_type, source_url, title, content, 
                       published_date, filing_type, metadata_json) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        company_id,
                        "sec_filing",
                        f["document_url"],
                        f"{f['form_type']} - {f['description']}",
                        content,
                        f["filing_date"],
                        f["form_type"],
                        json.dumps(f),
                    )
                )
                ingested += 1

        await db.commit()
        return {"status": "success", "documents_ingested": ingested, "total_found": len(filings)}

    finally:
        await db.close()
