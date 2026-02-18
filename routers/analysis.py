"""
API routes for analysis modules and diagnostic reports.
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from models.database import get_db
from services.analysis_engine import (
    extract_narrative_themes,
    detect_governance_signals,
    detect_narrative_collisions,
    compute_issue_accumulation,
    generate_diagnostic_report,
)
from services.report_generator import generate_pdf_report

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# --- Module 1: Narrative Positioning ---
@router.post("/{company_id}/narrative")
async def run_narrative_analysis(company_id: int):
    """Run narrative theme extraction and scoring."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    result = await extract_narrative_themes(company_id, company["ticker"])
    return result


@router.get("/{company_id}/narrative")
async def get_narrative_scores(company_id: int):
    """Get narrative positioning scores."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM narrative_scores WHERE company_id = ? ORDER BY computed_at DESC LIMIT 20",
            (company_id,)
        )
        scores = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM narrative_themes WHERE company_id = ? ORDER BY extracted_at DESC LIMIT 30",
            (company_id,)
        )
        themes = [dict(r) for r in await cursor.fetchall()]

        return {"scores": scores, "themes": themes}
    finally:
        await db.close()


# --- Module 2: Governance Pressure ---
@router.post("/{company_id}/governance")
async def run_governance_analysis(company_id: int):
    """Run governance signal detection."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    result = await detect_governance_signals(company_id, company["ticker"])
    return result


@router.get("/{company_id}/governance")
async def get_governance_scores(company_id: int):
    """Get governance pressure scores and signals."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM governance_scores WHERE company_id = ? ORDER BY computed_at DESC LIMIT 10",
            (company_id,)
        )
        scores = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM governance_signals WHERE company_id = ? ORDER BY detected_at DESC LIMIT 20",
            (company_id,)
        )
        signals = [dict(r) for r in await cursor.fetchall()]

        return {"scores": scores, "signals": signals}
    finally:
        await db.close()


# --- Module 3: Narrative Collisions ---
@router.post("/{company_id}/collisions")
async def run_collision_analysis(company_id: int):
    """Run narrative collision detection."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    result = await detect_narrative_collisions(company_id, company["ticker"])
    return result


@router.get("/{company_id}/collisions")
async def get_collisions(company_id: int):
    """Get detected narrative collisions."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM narrative_collisions WHERE company_id = ? ORDER BY detected_at DESC LIMIT 20",
            (company_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


# --- Module 4: Peer Exposure Map ---
@router.get("/{company_id}/peers/exposure")
async def get_peer_exposure(company_id: int):
    """Get peer exposure map comparison."""
    db = await get_db()
    try:
        # Get peers
        cursor = await db.execute(
            """SELECT c.* FROM companies c
               JOIN peer_groups pg ON c.id = pg.peer_company_id
               WHERE pg.company_id = ?""",
            (company_id,)
        )
        peers = [dict(r) for r in await cursor.fetchall()]

        if not peers:
            return {"message": "No peers configured. Add peers first.", "peers": []}

        peer_data = []
        for peer in peers:
            pid = peer["id"]

            # Get latest governance score
            cursor = await db.execute(
                "SELECT overall_pressure_score FROM governance_scores WHERE company_id = ? ORDER BY computed_at DESC LIMIT 1",
                (pid,)
            )
            gov = await cursor.fetchone()

            # Get document counts as activity proxy
            cursor = await db.execute(
                "SELECT source_type, COUNT(*) as cnt FROM documents WHERE company_id = ? GROUP BY source_type",
                (pid,)
            )
            doc_counts = {d["source_type"]: d["cnt"] for d in await cursor.fetchall()}

            # Get latest issue accumulation
            cursor = await db.execute(
                "SELECT total_score, direction, intensity FROM issue_accumulation WHERE company_id = ? ORDER BY score_date DESC LIMIT 1",
                (pid,)
            )
            issue = await cursor.fetchone()

            peer_data.append({
                "id": pid,
                "ticker": peer["ticker"],
                "name": peer["name"],
                "governance_pressure": gov["overall_pressure_score"] if gov else None,
                "issue_accumulation": dict(issue) if issue else None,
                "document_counts": doc_counts,
            })

        return {"company_id": company_id, "peers": peer_data}
    finally:
        await db.close()


# --- Module 5: Issue Accumulation ---
@router.post("/{company_id}/accumulation")
async def compute_accumulation(company_id: int):
    """Compute issue accumulation score."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    result = await compute_issue_accumulation(company_id, company["ticker"])
    return result


@router.get("/{company_id}/accumulation")
async def get_accumulation_history(company_id: int, limit: int = 30):
    """Get issue accumulation score history."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM issue_accumulation WHERE company_id = ? ORDER BY score_date DESC LIMIT ?",
            (company_id, limit)
        )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


# --- Diagnostic Reports ---
@router.post("/{company_id}/diagnostic")
async def generate_diagnostic(company_id: int, report_type: str = "weekly"):
    """Generate a full diagnostic report."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    result = await generate_diagnostic_report(company_id, company["ticker"], report_type)
    return result


@router.get("/{company_id}/diagnostics")
async def list_diagnostics(company_id: int):
    """List generated diagnostics."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, report_type, period, full_report_text, pdf_path, generated_at FROM diagnostics WHERE company_id = ? ORDER BY generated_at DESC LIMIT 20",
            (company_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


@router.get("/{company_id}/diagnostics/{diagnostic_id}")
async def get_diagnostic(company_id: int, diagnostic_id: int):
    """Get a specific diagnostic report."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM diagnostics WHERE id = ? AND company_id = ?",
            (diagnostic_id, company_id)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Diagnostic not found")

        data = dict(row)
        for key in ["narrative_shifts_json", "governance_indicators_json", "sector_risks_json", "advisory_implications_json"]:
            if data.get(key):
                data[key] = json.loads(data[key])

        return data
    finally:
        await db.close()


@router.post("/{company_id}/diagnostics/{diagnostic_id}/pdf")
async def generate_pdf(company_id: int, diagnostic_id: int):
    """Generate PDF for a diagnostic."""
    try:
        filepath = await generate_pdf_report(diagnostic_id)
        return FileResponse(filepath, media_type="application/pdf", filename=filepath.split("/")[-1])
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {str(e)}")


# --- Alerts ---
@router.get("/{company_id}/alerts")
async def get_alerts(company_id: int, unacknowledged_only: bool = True):
    """Get alerts for a company."""
    db = await get_db()
    try:
        if unacknowledged_only:
            cursor = await db.execute(
                "SELECT * FROM alerts WHERE company_id = ? AND acknowledged = 0 ORDER BY created_at DESC",
                (company_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM alerts WHERE company_id = ? ORDER BY created_at DESC LIMIT 50",
                (company_id,)
            )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


@router.post("/{company_id}/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(company_id: int, alert_id: int):
    """Acknowledge an alert."""
    db = await get_db()
    try:
        await db.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ? AND company_id = ?", (alert_id, company_id))
        await db.commit()
        return {"status": "acknowledged"}
    finally:
        await db.close()


# --- Full Pipeline ---
@router.post("/{company_id}/run-full-pipeline")
async def run_full_pipeline(company_id: int):
    """Run the complete analysis pipeline: ingest → analyze → score → report."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = await cursor.fetchone()
        if not company:
            raise HTTPException(404, "Company not found")
    finally:
        await db.close()

    ticker = company["ticker"]
    name = company["name"]
    results = {"company": ticker, "steps": {}}

    # Step 1: Ingest data
    from services.sec_ingestion import ingest_sec_filings
    from services.news_ingestion import ingest_news, ingest_press_releases

    try:
        results["steps"]["sec_ingestion"] = await ingest_sec_filings(company_id, ticker)
    except Exception as e:
        results["steps"]["sec_ingestion"] = {"status": "error", "message": str(e)}

    try:
        results["steps"]["news_ingestion"] = await ingest_news(company_id, ticker, name)
    except Exception as e:
        results["steps"]["news_ingestion"] = {"status": "error", "message": str(e)}

    try:
        results["steps"]["press_ingestion"] = await ingest_press_releases(company_id, ticker, name)
    except Exception as e:
        results["steps"]["press_ingestion"] = {"status": "error", "message": str(e)}

    # Step 2: Run analysis modules
    try:
        results["steps"]["narrative_analysis"] = await extract_narrative_themes(company_id, ticker)
    except Exception as e:
        results["steps"]["narrative_analysis"] = {"status": "error", "message": str(e)}

    try:
        results["steps"]["governance_analysis"] = await detect_governance_signals(company_id, ticker)
    except Exception as e:
        results["steps"]["governance_analysis"] = {"status": "error", "message": str(e)}

    try:
        results["steps"]["collision_analysis"] = await detect_narrative_collisions(company_id, ticker)
    except Exception as e:
        results["steps"]["collision_analysis"] = {"status": "error", "message": str(e)}

    # Step 3: Compute issue accumulation
    try:
        results["steps"]["issue_accumulation"] = await compute_issue_accumulation(company_id, ticker)
    except Exception as e:
        results["steps"]["issue_accumulation"] = {"status": "error", "message": str(e)}

    # Step 4: Generate diagnostic
    try:
        results["steps"]["diagnostic"] = await generate_diagnostic_report(company_id, ticker)
    except Exception as e:
        results["steps"]["diagnostic"] = {"status": "error", "message": str(e)}

    return results
