"""
API routes for company management.
"""

from fastapi import APIRouter, HTTPException
from models.schemas import CompanyCreate, CompanyResponse, PeerGroupSet
from models.database import get_db

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.post("/", response_model=CompanyResponse)
async def create_company(company: CompanyCreate):
    db = await get_db()
    try:
        # Check for duplicate ticker
        existing = await db.execute("SELECT id FROM companies WHERE ticker = ?", (company.ticker.upper(),))
        if await existing.fetchone():
            raise HTTPException(400, f"Company with ticker {company.ticker} already exists")

        # Look up CIK if not provided
        cik = company.cik
        if not cik:
            try:
                from services.sec_ingestion import lookup_cik
                cik = await lookup_cik(company.ticker)
            except Exception:
                cik = None  # CIK lookup is optional; will retry during ingestion

        cursor = await db.execute(
            "INSERT INTO companies (name, ticker, sector, cik, description) VALUES (?, ?, ?, ?, ?)",
            (company.name, company.ticker.upper(), company.sector, cik, company.description)
        )
        await db.commit()
        company_id = cursor.lastrowid

        return CompanyResponse(
            id=company_id,
            name=company.name,
            ticker=company.ticker.upper(),
            sector=company.sector,
            cik=cik,
            description=company.description,
            created_at="",
            peer_ids=[],
        )
    finally:
        await db.close()


@router.get("/")
async def list_companies():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies ORDER BY name")
        rows = await cursor.fetchall()
        companies = []
        for r in rows:
            # Get peer IDs
            peer_cursor = await db.execute(
                "SELECT peer_company_id FROM peer_groups WHERE company_id = ?", (r["id"],)
            )
            peers = [p["peer_company_id"] for p in await peer_cursor.fetchall()]
            companies.append({**dict(r), "peer_ids": peers})
        return companies
    finally:
        await db.close()


@router.get("/{company_id}")
async def get_company(company_id: int):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Company not found")

        peer_cursor = await db.execute(
            "SELECT peer_company_id FROM peer_groups WHERE company_id = ?", (company_id,)
        )
        peers = [p["peer_company_id"] for p in await peer_cursor.fetchall()]

        # Get document counts
        doc_cursor = await db.execute(
            "SELECT source_type, COUNT(*) as cnt FROM documents WHERE company_id = ? GROUP BY source_type",
            (company_id,)
        )
        doc_counts = {d["source_type"]: d["cnt"] for d in await doc_cursor.fetchall()}

        return {**dict(row), "peer_ids": peers, "document_counts": doc_counts}
    finally:
        await db.close()


@router.post("/{company_id}/peers")
async def set_peers(company_id: int, peer_set: PeerGroupSet):
    db = await get_db()
    try:
        # Verify company exists
        cursor = await db.execute("SELECT id FROM companies WHERE id = ?", (company_id,))
        if not await cursor.fetchone():
            raise HTTPException(404, "Company not found")

        # Clear existing peers
        await db.execute("DELETE FROM peer_groups WHERE company_id = ?", (company_id,))

        added = []
        for ticker in peer_set.peer_ticker_list:
            cursor = await db.execute("SELECT id FROM companies WHERE ticker = ?", (ticker.upper(),))
            peer = await cursor.fetchone()
            if peer:
                await db.execute(
                    "INSERT OR IGNORE INTO peer_groups (company_id, peer_company_id) VALUES (?, ?)",
                    (company_id, peer["id"])
                )
                added.append(ticker.upper())

        await db.commit()
        return {"status": "success", "peers_linked": added}
    finally:
        await db.close()


@router.delete("/{company_id}")
async def delete_company(company_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        await db.commit()
        return {"status": "deleted"}
    finally:
        await db.close()
