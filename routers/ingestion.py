"""
API routes for data ingestion.
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from models.schemas import IngestionTrigger
from models.database import get_db
from services.sec_ingestion import ingest_sec_filings
from services.news_ingestion import ingest_news, ingest_press_releases

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


async def _run_ingestion(company_id: int, ticker: str, company_name: str, source_types: list[str]):
    """Background ingestion task."""
    db = await get_db()
    try:
        for source_type in source_types:
            log_cursor = await db.execute(
                "INSERT INTO ingestion_log (company_id, source_type, status) VALUES (?, ?, ?)",
                (company_id, source_type, "running")
            )
            log_id = log_cursor.lastrowid
            await db.commit()

            try:
                if source_type == "sec_filing":
                    result = await ingest_sec_filings(company_id, ticker)
                elif source_type == "news":
                    result = await ingest_news(company_id, ticker, company_name)
                elif source_type == "press_release":
                    result = await ingest_press_releases(company_id, ticker, company_name)
                else:
                    result = {"status": "skipped", "message": f"Unknown source type: {source_type}"}

                status = result.get("status", "error")
                doc_count = result.get("documents_ingested", 0)

                await db.execute(
                    "UPDATE ingestion_log SET status = ?, documents_count = ?, completed_at = ? WHERE id = ?",
                    (status, doc_count, datetime.now().isoformat(), log_id)
                )
            except Exception as e:
                await db.execute(
                    "UPDATE ingestion_log SET status = ?, error_message = ?, completed_at = ? WHERE id = ?",
                    ("error", str(e), datetime.now().isoformat(), log_id)
                )

            await db.commit()
    finally:
        await db.close()


@router.post("/{company_id}")
async def trigger_ingestion(company_id: int, trigger: IngestionTrigger, background_tasks: BackgroundTasks):
    """Trigger data ingestion for a company."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")

        background_tasks.add_task(
            _run_ingestion,
            company_id,
            company["ticker"],
            company["name"],
            trigger.source_types
        )

        return {
            "status": "ingestion_started",
            "company": company["ticker"],
            "source_types": trigger.source_types,
        }
    finally:
        await db.close()


@router.post("/{company_id}/sync")
async def sync_ingestion(company_id: int, trigger: IngestionTrigger):
    """Synchronous ingestion — waits for completion."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    results = {}
    for source_type in trigger.source_types:
        try:
            if source_type == "sec_filing":
                results[source_type] = await ingest_sec_filings(company_id, company["ticker"])
            elif source_type == "news":
                results[source_type] = await ingest_news(company_id, company["ticker"], company["name"])
            elif source_type == "press_release":
                results[source_type] = await ingest_press_releases(company_id, company["ticker"], company["name"])
        except Exception as e:
            results[source_type] = {"status": "error", "message": str(e)}

    return {"company": company["ticker"], "results": results}


@router.get("/{company_id}/status")
async def ingestion_status(company_id: int):
    """Get ingestion log for a company."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM ingestion_log WHERE company_id = ? ORDER BY started_at DESC LIMIT 20",
            (company_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


@router.get("/{company_id}/documents")
async def list_documents(company_id: int, source_type: str = None, limit: int = 50):
    """List ingested documents for a company."""
    db = await get_db()
    try:
        if source_type:
            cursor = await db.execute(
                "SELECT id, source_type, title, source_url, published_date, filing_type, ingested_at FROM documents WHERE company_id = ? AND source_type = ? ORDER BY published_date DESC LIMIT ?",
                (company_id, source_type, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT id, source_type, title, source_url, published_date, filing_type, ingested_at FROM documents WHERE company_id = ? ORDER BY published_date DESC LIMIT ?",
                (company_id, limit)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
