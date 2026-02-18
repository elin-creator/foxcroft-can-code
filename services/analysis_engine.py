"""
Analysis engine using Anthropic Claude API for narrative extraction,
governance signal detection, and collision analysis.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
import anthropic
from models.database import get_db

# Initialize client — will use ANTHROPIC_API_KEY env var
def get_client():
    return anthropic.Anthropic()

MODEL = "claude-sonnet-4-20250514"


async def extract_narrative_themes(company_id: int, ticker: str) -> dict:
    """
    Module 1: Narrative Positioning Index.
    Analyze recent documents to extract recurring strategic themes.
    """
    db = await get_db()
    try:
        # Fetch recent documents
        cursor = await db.execute(
            """SELECT id, source_type, title, content, published_date, filing_type
               FROM documents WHERE company_id = ?
               ORDER BY published_date DESC LIMIT 20""",
            (company_id,)
        )
        docs = await cursor.fetchall()

        if not docs:
            return {"status": "no_data", "message": "No documents found for analysis"}

        # Build context for Claude
        doc_summaries = []
        for d in docs:
            content_preview = d["content"][:3000] if d["content"] else ""
            doc_summaries.append(
                f"[{d['source_type']} | {d['filing_type'] or 'N/A'} | {d['published_date']}] "
                f"{d['title']}\n{content_preview}"
            )

        docs_text = "\n\n---\n\n".join(doc_summaries)

        prompt = f"""Analyze the following public documents for {ticker} and extract the strategic narrative positioning.

DOCUMENTS:
{docs_text}

Perform the following analysis and return ONLY valid JSON (no markdown):

{{
    "themes": [
        {{
            "theme": "theme name (e.g., 'Transformation', 'Cost Discipline', 'Innovation Leadership')",
            "frequency": 0.0-1.0,
            "channels_present": ["earnings", "filing", "media", "press_release"],
            "consistency_score": 0.0-1.0,
            "defensive_language_detected": true/false,
            "trend": "increasing/stable/decreasing",
            "supporting_excerpts": ["brief quote 1", "brief quote 2"]
        }}
    ],
    "narrative_shifts": [
        {{
            "description": "description of shift",
            "from_theme": "previous emphasis",
            "to_theme": "new emphasis",
            "severity": 0.0-1.0,
            "evidence": "brief supporting evidence"
        }}
    ],
    "new_defensive_language": [
        {{
            "phrase_pattern": "the defensive language pattern",
            "context": "where it appeared",
            "implication": "what it might signal"
        }}
    ],
    "summary": "2-3 sentence strategic narrative assessment"
}}

Focus on:
1. Recurring strategic themes and their frequency across channels
2. Whether language is consistent across earnings calls, filings, and press
3. Any abrupt shifts in emphasis
4. Emergence of defensive or hedging language
5. Divergence from what you know about typical sector language"""

        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text
        # Clean potential markdown wrapping
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            result_text = result_text.rsplit("```", 1)[0]

        result = json.loads(result_text)

        # Store themes in database
        quarter = f"{datetime.now().year}-Q{(datetime.now().month - 1) // 3 + 1}"
        for theme in result.get("themes", []):
            await db.execute(
                """INSERT INTO narrative_themes (company_id, theme, confidence, channel, quarter, raw_excerpt)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    company_id,
                    theme["theme"],
                    theme["frequency"],
                    ",".join(theme.get("channels_present", [])),
                    quarter,
                    json.dumps(theme.get("supporting_excerpts", [])),
                )
            )

            # Store aggregated score
            await db.execute(
                """INSERT INTO narrative_scores (company_id, period, theme, frequency_score,
                   consistency_score, peer_divergence_score, defensive_language_score, overall_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    company_id,
                    quarter,
                    theme["theme"],
                    theme["frequency"],
                    theme["consistency_score"],
                    0.0,  # peer divergence computed separately
                    1.0 if theme.get("defensive_language_detected") else 0.0,
                    theme["frequency"] * 0.4 + theme["consistency_score"] * 0.3 +
                    (1.0 if theme.get("defensive_language_detected") else 0.0) * 0.3,
                )
            )

        await db.commit()
        return {"status": "success", "result": result}

    finally:
        await db.close()


async def detect_governance_signals(company_id: int, ticker: str) -> dict:
    """
    Module 2: Governance and Board Pressure Tracker.
    Analyze documents for governance-related signals.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, source_type, title, content, published_date, filing_type
               FROM documents WHERE company_id = ?
               AND (source_type IN ('sec_filing', 'news', 'press_release')
                    OR filing_type IN ('DEF 14A', 'DEFA14A', 'SC 13D', 'SC 13D/A', '8-K'))
               ORDER BY published_date DESC LIMIT 25""",
            (company_id,)
        )
        docs = await cursor.fetchall()

        if not docs:
            return {"status": "no_data", "message": "No documents found for governance analysis"}

        doc_summaries = []
        for d in docs:
            content_preview = d["content"][:3000] if d["content"] else ""
            doc_summaries.append(
                f"[{d['source_type']} | {d['filing_type'] or 'N/A'} | {d['published_date']}] "
                f"{d['title']}\n{content_preview}"
            )

        docs_text = "\n\n---\n\n".join(doc_summaries)

        prompt = f"""Analyze the following public documents for {ticker} and detect governance-related signals.

DOCUMENTS:
{docs_text}

Return ONLY valid JSON (no markdown):

{{
    "signals": [
        {{
            "signal_type": "board_change|proxy_dissent|comp_controversy|activist_filing|analyst_governance|committee_change|executive_departure|regulatory_scrutiny",
            "description": "description of the signal",
            "severity": 0.0-1.0,
            "source_date": "YYYY-MM-DD or null",
            "evidence": "brief supporting evidence"
        }}
    ],
    "pressure_scores": {{
        "governance_reference_volume": 0.0-1.0,
        "proxy_dissent_indicators": 0.0-1.0,
        "activist_rhetoric_score": 0.0-1.0,
        "comp_controversy_score": 0.0-1.0,
        "sector_scrutiny_score": 0.0-1.0,
        "overall_pressure": 0.0-1.0
    }},
    "board_composition_changes": [
        {{
            "change": "description",
            "date": "YYYY-MM-DD or null",
            "significance": "low|medium|high"
        }}
    ],
    "summary": "2-3 sentence governance pressure assessment"
}}

Focus on:
1. Board composition changes and committee assignments
2. Proxy voting outcomes and shareholder proposal trends
3. Executive compensation concerns
4. Activist investor activity or rhetoric
5. Analyst commentary on governance
6. Regulatory scrutiny indicators"""

        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            result_text = result_text.rsplit("```", 1)[0]

        result = json.loads(result_text)

        # Store signals
        for signal in result.get("signals", []):
            await db.execute(
                """INSERT INTO governance_signals (company_id, signal_type, description,
                   severity, source_date, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    company_id,
                    signal["signal_type"],
                    signal["description"],
                    signal["severity"],
                    signal.get("source_date"),
                    json.dumps(signal),
                )
            )

        # Store aggregated score
        scores = result.get("pressure_scores", {})
        period = f"{datetime.now().year}-W{datetime.now().isocalendar()[1]:02d}"
        await db.execute(
            """INSERT INTO governance_scores (company_id, period, governance_reference_volume,
               proxy_dissent_delta, activist_rhetoric_score, comp_controversy_score,
               sector_scrutiny_score, overall_pressure_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company_id,
                period,
                scores.get("governance_reference_volume", 0),
                scores.get("proxy_dissent_indicators", 0),
                scores.get("activist_rhetoric_score", 0),
                scores.get("comp_controversy_score", 0),
                scores.get("sector_scrutiny_score", 0),
                scores.get("overall_pressure", 0),
            )
        )

        await db.commit()
        return {"status": "success", "result": result}

    finally:
        await db.close()


async def detect_narrative_collisions(company_id: int, ticker: str) -> dict:
    """
    Module 3: Narrative Collision Detector.
    Compare internal claims vs. performance disclosures vs. media framing.
    """
    db = await get_db()
    try:
        # Get internal claims (earnings, filings)
        cursor = await db.execute(
            """SELECT source_type, title, content, published_date FROM documents
               WHERE company_id = ? AND source_type IN ('sec_filing', 'press_release')
               ORDER BY published_date DESC LIMIT 10""",
            (company_id,)
        )
        internal_docs = await cursor.fetchall()

        # Get external framing (news)
        cursor = await db.execute(
            """SELECT source_type, title, content, published_date FROM documents
               WHERE company_id = ? AND source_type = 'news'
               ORDER BY published_date DESC LIMIT 10""",
            (company_id,)
        )
        external_docs = await cursor.fetchall()

        if not internal_docs and not external_docs:
            return {"status": "no_data", "message": "Insufficient documents for collision analysis"}

        internal_text = "\n\n---\n\n".join([
            f"[{d['source_type']} | {d['published_date']}] {d['title']}\n{d['content'][:2000]}"
            for d in internal_docs
        ])

        external_text = "\n\n---\n\n".join([
            f"[{d['source_type']} | {d['published_date']}] {d['title']}\n{d['content'][:2000]}"
            for d in external_docs
        ])

        prompt = f"""Analyze these two sets of documents for {ticker} and detect narrative collisions — 
where the company's public claims diverge from what performance data, media coverage, or analyst framing suggest.

COMPANY INTERNAL DOCUMENTS (filings, press releases):
{internal_text}

EXTERNAL COVERAGE (news, analyst):
{external_text}

Return ONLY valid JSON:

{{
    "collisions": [
        {{
            "claim_source": "earnings_call|filing|press_release",
            "claim_summary": "what the company claims",
            "contradicting_source": "news|analyst|performance_data",
            "contradiction_summary": "what contradicts or tensions with the claim",
            "tension_type": "performance_gap|media_divergence|analyst_divergence|narrative_inconsistency",
            "severity": 0.0-1.0,
            "evidence": "specific supporting evidence"
        }}
    ],
    "perception_risk_areas": [
        {{
            "area": "area of risk",
            "description": "why this matters",
            "urgency": "low|medium|high"
        }}
    ],
    "summary": "2-3 sentence collision assessment focusing on where perception diverges from positioning"
}}

Look for CONCEPTUAL tension, not just wording differences. For example:
- Claiming "operational discipline" while disclosing rising restructuring charges
- Stating "growth acceleration" while media reports execution concerns
- Emphasizing "innovation leadership" while R&D spend is declining"""

        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            result_text = result_text.rsplit("```", 1)[0]

        result = json.loads(result_text)

        # Store collisions
        period = f"{datetime.now().year}-W{datetime.now().isocalendar()[1]:02d}"
        for collision in result.get("collisions", []):
            await db.execute(
                """INSERT INTO narrative_collisions (company_id, claim_source, claim_summary,
                   contradicting_source, contradiction_summary, tension_type, severity, period)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    company_id,
                    collision["claim_source"],
                    collision["claim_summary"],
                    collision["contradicting_source"],
                    collision["contradiction_summary"],
                    collision["tension_type"],
                    collision["severity"],
                    period,
                )
            )

        await db.commit()
        return {"status": "success", "result": result}

    finally:
        await db.close()


async def compute_issue_accumulation(company_id: int, ticker: str) -> dict:
    """
    Module 5: Issue Accumulation Score.
    Compute rolling 90-day weighted score across all signal types.
    """
    db = await get_db()
    try:
        ninety_days_ago = (datetime.now() - timedelta(days=90)).isoformat()

        # Count governance signals
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt, AVG(severity) as avg_sev FROM governance_signals WHERE company_id = ? AND detected_at > ?",
            (company_id, ninety_days_ago)
        )
        gov_row = await cursor.fetchone()
        gov_count = gov_row["cnt"] or 0
        gov_severity = gov_row["avg_sev"] or 0

        # Count narrative collisions
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt, AVG(severity) as avg_sev FROM narrative_collisions WHERE company_id = ? AND detected_at > ?",
            (company_id, ninety_days_ago)
        )
        collision_row = await cursor.fetchone()
        collision_count = collision_row["cnt"] or 0
        collision_severity = collision_row["avg_sev"] or 0

        # Count news volume (media velocity proxy)
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM documents WHERE company_id = ? AND source_type = 'news' AND ingested_at > ?",
            (company_id, ninety_days_ago)
        )
        news_row = await cursor.fetchone()
        news_count = news_row["cnt"] or 0

        # Get latest governance pressure score
        cursor = await db.execute(
            "SELECT overall_pressure_score FROM governance_scores WHERE company_id = ? ORDER BY computed_at DESC LIMIT 1",
            (company_id,)
        )
        gov_score_row = await cursor.fetchone()
        gov_pressure = gov_score_row["overall_pressure_score"] if gov_score_row else 0

        # Weighted computation
        governance_weight = min(gov_severity * (gov_count / 5), 1.0)
        investor_impact = gov_pressure * 0.7 + (collision_severity * 0.3)
        regulatory_weight = min(gov_count * 0.15, 1.0)  # rough proxy
        narrative_contradiction = min(collision_count * collision_severity / 3, 1.0)
        media_velocity = min(news_count / 20, 1.0)  # normalized to ~20 articles as baseline

        total = (
            governance_weight * 0.25 +
            investor_impact * 0.25 +
            regulatory_weight * 0.15 +
            narrative_contradiction * 0.20 +
            media_velocity * 0.15
        )

        # Determine direction by comparing to previous score
        cursor = await db.execute(
            "SELECT total_score FROM issue_accumulation WHERE company_id = ? ORDER BY score_date DESC LIMIT 1",
            (company_id,)
        )
        prev = await cursor.fetchone()
        prev_score = prev["total_score"] if prev else 0

        if total > prev_score + 0.05:
            direction = "increasing"
        elif total < prev_score - 0.05:
            direction = "decreasing"
        else:
            direction = "stable"

        if total < 0.25:
            intensity = "low"
        elif total < 0.50:
            intensity = "moderate"
        elif total < 0.75:
            intensity = "elevated"
        else:
            intensity = "high"

        await db.execute(
            """INSERT INTO issue_accumulation (company_id, score_date, governance_weight,
               investor_impact_weight, regulatory_weight, narrative_contradiction_weight,
               media_velocity_weight, total_score, direction, intensity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company_id,
                datetime.now().strftime("%Y-%m-%d"),
                governance_weight,
                investor_impact,
                regulatory_weight,
                narrative_contradiction,
                media_velocity,
                total,
                direction,
                intensity,
            )
        )

        await db.commit()

        return {
            "status": "success",
            "result": {
                "total_score": round(total, 3),
                "direction": direction,
                "intensity": intensity,
                "components": {
                    "governance": round(governance_weight, 3),
                    "investor_impact": round(investor_impact, 3),
                    "regulatory": round(regulatory_weight, 3),
                    "narrative_contradiction": round(narrative_contradiction, 3),
                    "media_velocity": round(media_velocity, 3),
                },
            }
        }

    finally:
        await db.close()


async def generate_diagnostic_report(company_id: int, ticker: str, report_type: str = "weekly") -> dict:
    """
    Generate a comprehensive diagnostic report combining all modules.
    """
    db = await get_db()
    try:
        # Gather all recent analysis data
        cursor = await db.execute(
            "SELECT * FROM narrative_scores WHERE company_id = ? ORDER BY computed_at DESC LIMIT 10",
            (company_id,)
        )
        narrative_data = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM governance_scores WHERE company_id = ? ORDER BY computed_at DESC LIMIT 5",
            (company_id,)
        )
        governance_data = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM narrative_collisions WHERE company_id = ? ORDER BY detected_at DESC LIMIT 10",
            (company_id,)
        )
        collision_data = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM issue_accumulation WHERE company_id = ? ORDER BY score_date DESC LIMIT 5",
            (company_id,)
        )
        accumulation_data = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM governance_signals WHERE company_id = ? ORDER BY detected_at DESC LIMIT 10",
            (company_id,)
        )
        signals_data = [dict(r) for r in await cursor.fetchall()]

        # Get alerts
        cursor = await db.execute(
            "SELECT * FROM alerts WHERE company_id = ? AND acknowledged = 0 ORDER BY created_at DESC LIMIT 5",
            (company_id,)
        )
        alerts_data = [dict(r) for r in await cursor.fetchall()]

        context = json.dumps({
            "narrative_scores": narrative_data,
            "governance_scores": governance_data,
            "collisions": collision_data,
            "issue_accumulation": accumulation_data,
            "governance_signals": signals_data,
            "active_alerts": alerts_data,
        }, indent=2, default=str)

        prompt = f"""You are generating a {report_type} strategic diagnostic report for {ticker}.

Here is the analysis data from all monitoring modules:
{context}

Generate a concise, partner-level diagnostic report. Return ONLY valid JSON:

{{
    "narrative_shifts": [
        {{
            "title": "shift title",
            "description": "what shifted and why it matters",
            "severity": "low|medium|high",
            "advisory_note": "what to watch or consider"
        }}
    ],
    "governance_indicators": [
        {{
            "title": "indicator title",
            "description": "what the data shows",
            "severity": "low|medium|high",
            "advisory_note": "what to watch or consider"
        }}
    ],
    "sector_risks": [
        {{
            "title": "risk title",
            "description": "sector-level pressure that could migrate to client",
            "probability": "low|medium|high"
        }}
    ],
    "advisory_implications": [
        {{
            "implication": "the strategic implication",
            "options": ["option 1", "option 2"],
            "timing": "immediate|next_quarter|monitoring"
        }}
    ],
    "executive_summary": "3-5 sentence executive summary suitable for a partner briefing. Focus on direction and intensity, not individual data points. Frame as advisory implications, not recommendations."
}}

Rules:
- Top 3 items in each category maximum
- Advisory implications framed as OPTIONS, not recommendations
- Use conditional language: 'If X continues, consider Y'
- Focus on what has changed, not the current state"""

        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            result_text = result_text.rsplit("```", 1)[0]

        result = json.loads(result_text)

        period = f"{datetime.now().year}-W{datetime.now().isocalendar()[1]:02d}"

        await db.execute(
            """INSERT INTO diagnostics (company_id, report_type, period, narrative_shifts_json,
               governance_indicators_json, sector_risks_json, advisory_implications_json, full_report_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company_id,
                report_type,
                period,
                json.dumps(result.get("narrative_shifts", [])),
                json.dumps(result.get("governance_indicators", [])),
                json.dumps(result.get("sector_risks", [])),
                json.dumps(result.get("advisory_implications", [])),
                result.get("executive_summary", ""),
            )
        )

        await db.commit()
        return {"status": "success", "result": result}

    finally:
        await db.close()
