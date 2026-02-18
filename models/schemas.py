"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Company ---
class CompanyCreate(BaseModel):
    name: str
    ticker: str
    sector: Optional[str] = None
    cik: Optional[str] = None
    description: Optional[str] = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    ticker: str
    sector: Optional[str]
    cik: Optional[str]
    description: Optional[str]
    created_at: str
    peer_ids: list[int] = []


class PeerGroupSet(BaseModel):
    peer_ticker_list: list[str]


# --- Narrative ---
class NarrativeThemeResponse(BaseModel):
    theme: str
    frequency_score: float
    consistency_score: float
    peer_divergence_score: float
    defensive_language_score: float
    overall_score: float
    trend: str = "stable"  # increasing, stable, decreasing


class NarrativeIndexResponse(BaseModel):
    company_id: int
    ticker: str
    period: str
    themes: list[NarrativeThemeResponse]
    summary: str


# --- Governance ---
class GovernanceSignalResponse(BaseModel):
    signal_type: str
    description: str
    severity: float
    source_date: Optional[str]


class GovernancePressureResponse(BaseModel):
    company_id: int
    ticker: str
    period: str
    overall_pressure_score: float
    governance_reference_volume: float
    proxy_dissent_delta: float
    activist_rhetoric_score: float
    comp_controversy_score: float
    sector_scrutiny_score: float
    recent_signals: list[GovernanceSignalResponse]
    summary: str


# --- Collision ---
class NarrativeCollisionResponse(BaseModel):
    claim_summary: str
    contradiction_summary: str
    tension_type: str
    severity: float
    claim_source: str
    contradicting_source: str


class CollisionReportResponse(BaseModel):
    company_id: int
    ticker: str
    period: str
    collisions: list[NarrativeCollisionResponse]
    summary: str


# --- Peer Map ---
class PeerExposureItem(BaseModel):
    ticker: str
    name: str
    coverage_tone: float
    regulatory_scrutiny: float
    activist_filings: int
    executive_turnover: int
    litigation_exposure: float
    policy_references: int


class PeerExposureMapResponse(BaseModel):
    company_id: int
    ticker: str
    period: str
    peers: list[PeerExposureItem]
    sector_pressure_summary: str


# --- Issue Accumulation ---
class IssueAccumulationResponse(BaseModel):
    company_id: int
    ticker: str
    score_date: str
    total_score: float
    direction: str
    intensity: str
    governance_weight: float
    investor_impact_weight: float
    regulatory_weight: float
    narrative_contradiction_weight: float
    media_velocity_weight: float
    rolling_90_day_trend: list[dict]


# --- Diagnostic Report ---
class DiagnosticResponse(BaseModel):
    id: int
    company_id: int
    report_type: str
    period: str
    narrative_shifts: list[dict]
    governance_indicators: list[dict]
    sector_risks: list[dict]
    advisory_implications: list[dict]
    full_report_text: str
    generated_at: str
    pdf_available: bool = False


# --- Alert ---
class AlertResponse(BaseModel):
    id: int
    company_id: int
    alert_type: str
    title: str
    description: str
    severity: str
    acknowledged: bool
    created_at: str


# --- Ingestion ---
class IngestionStatusResponse(BaseModel):
    company_id: int
    source_type: str
    status: str
    documents_count: int
    started_at: str
    completed_at: Optional[str]


class IngestionTrigger(BaseModel):
    source_types: list[str] = Field(
        default=["sec_filing", "news"],
        description="Which source types to ingest"
    )
