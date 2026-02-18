"""
PDF report generation for diagnostic outputs.
Uses weasyprint to generate styled PDF reports.
"""

import json
import os
from datetime import datetime
from jinja2 import Template
from models.database import get_db

REPORT_DIR = os.environ.get("PNGSM_REPORT_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "reports"))
os.makedirs(REPORT_DIR, exist_ok=True)

REPORT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @page { margin: 1.5cm; size: A4; }
    body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 10pt; line-height: 1.5; }
    .header { border-bottom: 3px solid #16213e; padding-bottom: 12px; margin-bottom: 20px; }
    .header h1 { font-size: 18pt; color: #16213e; margin: 0 0 4px 0; letter-spacing: -0.5px; }
    .header .meta { color: #666; font-size: 9pt; }
    .header .ticker { color: #0f3460; font-size: 14pt; font-weight: 600; }
    h2 { font-size: 12pt; color: #16213e; border-left: 4px solid #e94560; padding-left: 10px; margin-top: 24px; }
    .section { margin-bottom: 20px; }
    .card { background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; margin: 8px 0; }
    .card .title { font-weight: 700; font-size: 10pt; margin-bottom: 4px; }
    .card .desc { font-size: 9pt; color: #333; }
    .severity-high { border-left: 4px solid #e94560; }
    .severity-medium { border-left: 4px solid #f5a623; }
    .severity-low { border-left: 4px solid #4ecdc4; }
    .advisory { background: #16213e; color: white; border-radius: 4px; padding: 14px; margin: 8px 0; }
    .advisory .title { font-weight: 700; font-size: 10pt; margin-bottom: 6px; }
    .advisory .options { font-size: 9pt; margin-top: 6px; }
    .advisory .timing { font-size: 8pt; opacity: 0.8; margin-top: 4px; }
    .summary-box { background: #f0f4ff; border: 2px solid #16213e; border-radius: 6px; padding: 16px; margin: 16px 0; font-size: 10pt; }
    .score-bar { height: 8px; border-radius: 4px; background: #e0e0e0; margin: 6px 0; }
    .score-fill { height: 100%; border-radius: 4px; }
    .score-low .score-fill { background: #4ecdc4; }
    .score-moderate .score-fill { background: #f5a623; }
    .score-elevated .score-fill { background: #e94560; }
    .score-high .score-fill { background: #c0392b; }
    .footer { border-top: 1px solid #ccc; padding-top: 8px; margin-top: 30px; font-size: 7pt; color: #999; }
</style>
</head>
<body>
    <div class="header">
        <h1>Public Narrative & Governance Signal Monitor</h1>
        <div class="ticker">{{ ticker }}</div>
        <div class="meta">{{ report_type | capitalize }} Diagnostic — {{ period }} — Generated {{ generated_at }}</div>
    </div>

    <div class="summary-box">
        <strong>Executive Summary</strong><br>
        {{ executive_summary }}
    </div>

    {% if issue_score %}
    <div class="section">
        <h2>Issue Accumulation Score</h2>
        <div class="card">
            <div class="title">90-Day Rolling Score: {{ "%.2f"|format(issue_score.total_score) }} — {{ issue_score.direction | capitalize }} / {{ issue_score.intensity | capitalize }}</div>
            <div class="score-bar score-{{ issue_score.intensity }}">
                <div class="score-fill" style="width: {{ (issue_score.total_score * 100)|int }}%"></div>
            </div>
        </div>
    </div>
    {% endif %}

    <div class="section">
        <h2>Top Narrative Shifts</h2>
        {% for item in narrative_shifts %}
        <div class="card severity-{{ item.severity }}">
            <div class="title">{{ item.title }}</div>
            <div class="desc">{{ item.description }}</div>
            {% if item.advisory_note %}<div class="desc" style="margin-top: 6px; font-style: italic;">→ {{ item.advisory_note }}</div>{% endif %}
        </div>
        {% endfor %}
        {% if not narrative_shifts %}<div class="card"><div class="desc">No significant narrative shifts detected this period.</div></div>{% endif %}
    </div>

    <div class="section">
        <h2>Governance Pressure Indicators</h2>
        {% for item in governance_indicators %}
        <div class="card severity-{{ item.severity }}">
            <div class="title">{{ item.title }}</div>
            <div class="desc">{{ item.description }}</div>
            {% if item.advisory_note %}<div class="desc" style="margin-top: 6px; font-style: italic;">→ {{ item.advisory_note }}</div>{% endif %}
        </div>
        {% endfor %}
        {% if not governance_indicators %}<div class="card"><div class="desc">No elevated governance pressure indicators this period.</div></div>{% endif %}
    </div>

    <div class="section">
        <h2>Sector Risk Movements</h2>
        {% for item in sector_risks %}
        <div class="card severity-{{ item.probability }}">
            <div class="title">{{ item.title }}</div>
            <div class="desc">{{ item.description }}</div>
        </div>
        {% endfor %}
        {% if not sector_risks %}<div class="card"><div class="desc">No notable sector-level pressure migration detected.</div></div>{% endif %}
    </div>

    <div class="section">
        <h2>Advisory Implications</h2>
        {% for item in advisory_implications %}
        <div class="advisory">
            <div class="title">{{ item.implication }}</div>
            <div class="options">
                {% for opt in item.options %}• {{ opt }}<br>{% endfor %}
            </div>
            <div class="timing">Timing: {{ item.timing | replace('_', ' ') | capitalize }}</div>
        </div>
        {% endfor %}
    </div>

    <div class="footer">
        CONFIDENTIAL — For internal advisory use only. Generated by Public Narrative & Governance Signal Monitor.
        All data sourced from public records. This output does not constitute legal, financial, or investment advice.
    </div>
</body>
</html>
"""


async def generate_pdf_report(diagnostic_id: int) -> str:
    """Generate a PDF from a stored diagnostic report."""
    from weasyprint import HTML

    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT d.*, c.ticker, c.name FROM diagnostics d
               JOIN companies c ON d.company_id = c.id
               WHERE d.id = ?""",
            (diagnostic_id,)
        )
        report = await cursor.fetchone()
        if not report:
            raise ValueError(f"Diagnostic {diagnostic_id} not found")

        # Get latest issue accumulation score
        cursor = await db.execute(
            "SELECT * FROM issue_accumulation WHERE company_id = ? ORDER BY score_date DESC LIMIT 1",
            (report["company_id"],)
        )
        issue_row = await cursor.fetchone()
        issue_score = dict(issue_row) if issue_row else None

        template = Template(REPORT_TEMPLATE)
        html_content = template.render(
            ticker=report["ticker"],
            company_name=report["name"],
            report_type=report["report_type"],
            period=report["period"],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            executive_summary=report["full_report_text"],
            narrative_shifts=json.loads(report["narrative_shifts_json"] or "[]"),
            governance_indicators=json.loads(report["governance_indicators_json"] or "[]"),
            sector_risks=json.loads(report["sector_risks_json"] or "[]"),
            advisory_implications=json.loads(report["advisory_implications_json"] or "[]"),
            issue_score=issue_score,
        )

        filename = f"{report['ticker']}_{report['report_type']}_{report['period']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        filepath = os.path.join(REPORT_DIR, filename)

        HTML(string=html_content).write_pdf(filepath)

        # Update diagnostic with PDF path
        await db.execute("UPDATE diagnostics SET pdf_path = ? WHERE id = ?", (filepath, diagnostic_id))
        await db.commit()

        return filepath

    finally:
        await db.close()
