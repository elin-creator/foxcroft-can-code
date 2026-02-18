# Signal Monitor

**Public Narrative & Governance Signal Monitor**

A continuously-updated intelligence platform that evaluates the external environment around public companies using only public data, detects pressure accumulation, and translates findings into partner-level advisory implications.

Designed for advisory firms that need to see narrative drift before clients do, identify governance pressure early, and anticipate activist or regulatory escalation — without creating reporting burden.

---

## Overview

Signal Monitor ingests public documents on a scheduled basis (SEC filings, news, press releases), runs them through five analysis modules powered by Claude, and produces weekly diagnostic reports with advisory implications framed as options rather than recommendations.

**The test for viability:** Would this system surface something meaningful 30 days before a board or CEO recognizes it themselves?

### Core Modules

| Module | Purpose |
|--------|---------|
| **Narrative Positioning Index** | Extracts recurring strategic themes, measures cross-channel consistency, flags defensive language shifts |
| **Governance & Board Pressure Tracker** | Monitors proxy dissent, board changes, compensation controversies, activist signals |
| **Narrative Collision Detector** | Identifies conceptual tension between company claims, performance disclosures, and media framing |
| **Peer & Sector Exposure Map** | Benchmarks client against defined peer set across governance, regulatory, and narrative metrics |
| **Issue Accumulation Score** | Rolling 90-day weighted composite score tracking direction and intensity across all signals |

### Outputs

- **Weekly one-page strategic diagnostic** — in-app view + downloadable PDF
- **Monthly board-level landscape summary** — aggregated diagnostic
- **Event-triggered alerts** — when threshold changes occur (e.g., governance score exceeds peer median by 25%)

---

## Quick Start

### Option 1: Docker (recommended)

```bash
git clone https://github.com/yourorg/signal-monitor.git
cd signal-monitor

# Configure your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Start
docker compose up -d

# Open http://localhost:8000
```

### Option 2: Local Python

```bash
git clone https://github.com/yourorg/signal-monitor.git
cd signal-monitor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set API key
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Run
python main.py
```

Open `http://localhost:8000` for the dashboard, or `http://localhost:8000/docs` for interactive API documentation.

---

## Usage

### 1. Add Companies

Add each company you want to monitor. The system will automatically look up the SEC CIK number.

```bash
POST /api/companies/
{"name": "CVS Health Corp", "ticker": "CVS", "sector": "Managed Care"}
```

### 2. Configure Peer Groups

Define which companies form the peer comparison set.

```bash
POST /api/companies/1/peers
{"peer_ticker_list": ["UNH", "CI", "HUM", "ELV"]}
```

### 3. Ingest Public Data

Pull SEC filings, news articles, and press releases from public sources.

```bash
POST /api/ingest/1/sync
{"source_types": ["sec_filing", "news", "press_release"]}
```

### 4. Run Full Analysis Pipeline

Executes all five modules sequentially: ingest → narrative extraction → governance detection → collision analysis → issue accumulation → diagnostic report.

```bash
POST /api/analysis/1/run-full-pipeline
```

### 5. Generate & Download Reports

```bash
# Generate diagnostic
POST /api/analysis/1/diagnostic

# Download as PDF
POST /api/analysis/1/diagnostics/{id}/pdf
```

All of these actions are also available through the dashboard UI.

---

## Architecture

```
signal-monitor/
├── main.py                       # FastAPI application entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
│
├── models/
│   ├── database.py               # SQLite schema, migrations, connection management
│   └── schemas.py                # Pydantic request/response models
│
├── services/
│   ├── sec_ingestion.py          # SEC EDGAR API integration (CIK lookup, filing fetch, full-text search)
│   ├── news_ingestion.py         # Google News RSS, Reuters, PR Newswire, Business Wire
│   ├── analysis_engine.py        # Claude API — all 5 analysis modules
│   └── report_generator.py       # PDF report generation via WeasyPrint + Jinja2
│
├── routers/
│   ├── companies.py              # Company CRUD, peer group management
│   ├── ingestion.py              # Data ingestion triggers, status, document listing
│   └── analysis.py               # Analysis modules, diagnostics, alerts, full pipeline
│
├── static/
│   └── index.html                # Single-page dashboard UI
│
└── data/                         # Created at runtime (gitignored)
    ├── monitor.db                # SQLite database
    └── reports/                  # Generated PDF reports
```

### Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **API** | FastAPI (Python) | Async support, auto-generated docs, Pydantic validation |
| **Database** | SQLite + aiosqlite | Zero-config, portable, sufficient for advisory-firm scale |
| **NLP Analysis** | Anthropic Claude API | Superior reasoning for theme extraction, collision detection, governance signal interpretation |
| **Data Sources** | SEC EDGAR API, RSS feeds | Free, public, no API keys required for ingestion |
| **PDF Reports** | WeasyPrint + Jinja2 | High-quality styled PDFs from HTML templates |
| **Frontend** | Vanilla HTML/CSS/JS | No build step, institutional design, zero dependencies |

---

## Data Sources

All public. No authentication required for ingestion.

| Source | Type | Method |
|--------|------|--------|
| **SEC EDGAR** | 10-K, 10-Q, 8-K, DEF 14A, SC 13D | REST API (`data.sec.gov`) |
| **Google News** | Company-specific coverage | RSS feed |
| **Reuters** | Business and company news | RSS feed |
| **PR Newswire** | Press releases | RSS feed |
| **Business Wire** | Press releases | RSS feed |
| **SEC Press** | Regulatory announcements | RSS feed |

---

## API Reference

### Companies

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/companies/` | Create company |
| `GET` | `/api/companies/` | List all companies |
| `GET` | `/api/companies/{id}` | Get company details + document counts |
| `POST` | `/api/companies/{id}/peers` | Set peer group |
| `DELETE` | `/api/companies/{id}` | Delete company |

### Ingestion

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ingest/{id}/sync` | Ingest data (synchronous, waits for completion) |
| `POST` | `/api/ingest/{id}` | Ingest data (background task) |
| `GET` | `/api/ingest/{id}/status` | Ingestion log |
| `GET` | `/api/ingest/{id}/documents` | List ingested documents |

### Analysis

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analysis/{id}/narrative` | Run narrative theme extraction |
| `GET` | `/api/analysis/{id}/narrative` | Get narrative scores and themes |
| `POST` | `/api/analysis/{id}/governance` | Run governance signal detection |
| `GET` | `/api/analysis/{id}/governance` | Get governance scores and signals |
| `POST` | `/api/analysis/{id}/collisions` | Run narrative collision detection |
| `GET` | `/api/analysis/{id}/collisions` | Get detected collisions |
| `POST` | `/api/analysis/{id}/accumulation` | Compute issue accumulation score |
| `GET` | `/api/analysis/{id}/accumulation` | Get accumulation history |
| `GET` | `/api/analysis/{id}/peers/exposure` | Get peer exposure map |
| `POST` | `/api/analysis/{id}/diagnostic` | Generate diagnostic report |
| `GET` | `/api/analysis/{id}/diagnostics` | List diagnostics |
| `GET` | `/api/analysis/{id}/diagnostics/{did}` | Get full diagnostic |
| `POST` | `/api/analysis/{id}/diagnostics/{did}/pdf` | Download PDF |
| `POST` | `/api/analysis/{id}/run-full-pipeline` | Run complete pipeline |
| `GET` | `/api/analysis/{id}/alerts` | Get active alerts |
| `POST` | `/api/analysis/{id}/alerts/{aid}/acknowledge` | Acknowledge alert |

Full interactive documentation available at `/docs` when the server is running.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for analysis) | — | Anthropic API key for Claude |
| `PNGSM_DB_PATH` | No | `./data/monitor.db` | SQLite database file path |

### Initial Setup

After first run, the system requires:

1. **Define companies** — Add each entity to monitor
2. **Set peer groups** — Link companies into comparison sets
3. **Initial ingestion** — First data pull (subsequent runs are incremental)

### Ongoing Operation

- **Daily/weekly ingestion** — Re-run ingestion to pull new documents (deduplicates automatically)
- **Weekly analysis** — Run the full pipeline to refresh all scores and generate diagnostics
- **Quarterly recalibration** — Review peer sets, theme weightings, and scoring thresholds

---

## Development

```bash
# Run in development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run tests (if added)
pytest tests/

# Check API docs
open http://localhost:8000/docs
```

### Adding New Data Sources

1. Create a new ingestion service in `services/` following the pattern in `sec_ingestion.py`
2. Add the source type to the `IngestionTrigger` schema
3. Wire it into the `_run_ingestion` function in `routers/ingestion.py`
4. Add it to the `run-full-pipeline` endpoint

### Extending Analysis

The analysis engine in `services/analysis_engine.py` uses structured prompts that return JSON. To modify analysis behavior, adjust the prompts and JSON schemas in each module function.

---

## License

MIT — see [LICENSE](LICENSE).
