"""
Database schema for the Public Narrative & Governance Signal Monitor.
Uses SQLite via aiosqlite for async operations.
"""

import aiosqlite
import os
from datetime import datetime

DB_PATH = os.environ.get("PNGSM_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "monitor.db"))

SCHEMA = """
-- Companies being tracked
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ticker TEXT UNIQUE NOT NULL,
    sector TEXT,
    cik TEXT,  -- SEC Central Index Key
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Peer group relationships
CREATE TABLE IF NOT EXISTS peer_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    peer_company_id INTEGER NOT NULL REFERENCES companies(id),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(company_id, peer_company_id)
);

-- Raw ingested documents
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    source_type TEXT NOT NULL,  -- 'sec_filing', 'press_release', 'news', 'earnings_call', 'analyst_note', 'proxy', 'regulator', 'activist'
    source_url TEXT,
    title TEXT,
    content TEXT,
    published_date TEXT,
    ingested_at TEXT DEFAULT (datetime('now')),
    filing_type TEXT,  -- '10-K', '10-Q', '8-K', 'DEF14A', etc.
    metadata_json TEXT  -- flexible metadata storage
);

-- Extracted narrative themes
CREATE TABLE IF NOT EXISTS narrative_themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    document_id INTEGER REFERENCES documents(id),
    theme TEXT NOT NULL,  -- e.g. 'Transformation', 'Cost discipline'
    confidence REAL,  -- 0.0 to 1.0
    channel TEXT,  -- 'earnings', 'filing', 'media', 'press_release'
    extracted_at TEXT DEFAULT (datetime('now')),
    quarter TEXT,  -- e.g. '2025-Q1'
    raw_excerpt TEXT  -- supporting text
);

-- Narrative Positioning Index scores (aggregated)
CREATE TABLE IF NOT EXISTS narrative_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    period TEXT NOT NULL,  -- e.g. '2025-W04' or '2025-Q1'
    theme TEXT NOT NULL,
    frequency_score REAL,
    consistency_score REAL,  -- cross-channel consistency
    peer_divergence_score REAL,
    defensive_language_score REAL,
    overall_score REAL,
    computed_at TEXT DEFAULT (datetime('now'))
);

-- Governance signals
CREATE TABLE IF NOT EXISTS governance_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    document_id INTEGER REFERENCES documents(id),
    signal_type TEXT NOT NULL,  -- 'board_change', 'proxy_dissent', 'comp_controversy', 'activist_filing', 'analyst_governance', 'committee_change'
    description TEXT,
    severity REAL,  -- 0.0 to 1.0
    detected_at TEXT DEFAULT (datetime('now')),
    source_date TEXT,
    metadata_json TEXT
);

-- Board Pressure Score (aggregated)
CREATE TABLE IF NOT EXISTS governance_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    period TEXT NOT NULL,
    governance_reference_volume REAL,
    proxy_dissent_delta REAL,
    activist_rhetoric_score REAL,
    comp_controversy_score REAL,
    sector_scrutiny_score REAL,
    overall_pressure_score REAL,
    computed_at TEXT DEFAULT (datetime('now'))
);

-- Narrative collisions (divergences between claims and reality)
CREATE TABLE IF NOT EXISTS narrative_collisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    claim_source TEXT,  -- 'earnings_call', 'press_release', etc.
    claim_summary TEXT,
    contradicting_source TEXT,
    contradiction_summary TEXT,
    tension_type TEXT,  -- 'performance_gap', 'media_divergence', 'analyst_divergence'
    severity REAL,
    detected_at TEXT DEFAULT (datetime('now')),
    period TEXT
);

-- Issue Accumulation Score (rolling)
CREATE TABLE IF NOT EXISTS issue_accumulation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    score_date TEXT NOT NULL,
    governance_weight REAL,
    investor_impact_weight REAL,
    regulatory_weight REAL,
    narrative_contradiction_weight REAL,
    media_velocity_weight REAL,
    total_score REAL,
    direction TEXT,  -- 'increasing', 'stable', 'decreasing'
    intensity TEXT,  -- 'low', 'moderate', 'elevated', 'high'
    computed_at TEXT DEFAULT (datetime('now'))
);

-- Weekly diagnostics (generated reports)
CREATE TABLE IF NOT EXISTS diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    report_type TEXT NOT NULL,  -- 'weekly', 'monthly', 'alert'
    period TEXT,
    narrative_shifts_json TEXT,
    governance_indicators_json TEXT,
    sector_risks_json TEXT,
    advisory_implications_json TEXT,
    full_report_text TEXT,
    pdf_path TEXT,
    generated_at TEXT DEFAULT (datetime('now'))
);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    alert_type TEXT NOT NULL,  -- 'governance_threshold', 'narrative_shift', 'peer_divergence', 'issue_accumulation'
    title TEXT,
    description TEXT,
    severity TEXT,  -- 'info', 'warning', 'critical'
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Ingestion log for tracking scheduled runs
CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    source_type TEXT,
    status TEXT,  -- 'success', 'error', 'partial'
    documents_count INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_company ON documents(company_id, source_type);
CREATE INDEX IF NOT EXISTS idx_documents_date ON documents(published_date);
CREATE INDEX IF NOT EXISTS idx_narrative_themes_company ON narrative_themes(company_id, theme);
CREATE INDEX IF NOT EXISTS idx_governance_signals_company ON governance_signals(company_id, signal_type);
CREATE INDEX IF NOT EXISTS idx_diagnostics_company ON diagnostics(company_id, report_type);
CREATE INDEX IF NOT EXISTS idx_alerts_company ON alerts(company_id, acknowledged);
"""


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()
