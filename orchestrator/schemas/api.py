"""
Request / Response Pydantic models for the EvidenceGate REST API.

Intentionally kept flat and JSON-serialisable — no nested Pydantic
sub-models beyond what FastAPI can handle trivially.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..core.models import MetricsSnapshot


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class RunGateRequest(BaseModel):
    topic: str = Field(
        min_length=5,
        max_length=500,
        description="The business idea / trend to evaluate (5–500 chars). Can be a short topic or a longer description / prompt.",
        examples=["fintech para PYMEs Ecuador"],
    )
    metrics: Optional[MetricsSnapshot] = Field(
        default=None,
        description="Real ad metrics, if already available. Omit for baseline run.",
    )


# ---------------------------------------------------------------------------
# Response — main gate run
# ---------------------------------------------------------------------------


class RunGateResponse(BaseModel):
    run_id: str = Field(description="UUID of this run")
    status: str = Field(description='"completed" | "failed"')
    idea_title: str
    verdict: str = Field(description='"pass" | "kill" | "iterate"')
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    next_steps: List[str]
    landing_headline: str
    landing_slug: str
    test_design: Dict = Field(description="EvidenceTestDesign serialised as dict")
    canonical_goal_statement: str
    steps_used: int
    cost_usd_estimated: float
    # Escalation
    needs_human_review: bool = False
    review_reason: Optional[str] = None
    ensemble_votes: Optional[List[str]] = None
    human_override: Optional[Dict] = None


# ---------------------------------------------------------------------------
# Human override (when ensemble disagrees and a founder decides manually)
# ---------------------------------------------------------------------------


class HumanOverrideRequest(BaseModel):
    verdict: str = Field(
        description='Final verdict chosen by the human: "pass" | "kill" | "iterate"',
        pattern="^(pass|kill|iterate)$",
    )
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Why this verdict — used for later calibration",
    )
    decided_by: str = Field(
        min_length=2,
        max_length=80,
        description="Name or email of the human deciding",
    )


class HumanOverrideResponse(BaseModel):
    run_id: str
    original_verdict: str
    override_verdict: str
    decided_by: str
    decided_at: str
    reason: str


class PendingReviewItem(BaseModel):
    run_id: str
    idea_title: str
    verdict: str
    confidence: float
    review_reason: str
    ensemble_votes: List[str]
    rationale: str


class PendingReviewResponse(BaseModel):
    pending_count: int
    items: List[PendingReviewItem]


# ---------------------------------------------------------------------------
# Lead capture (anti-bot protected)
# ---------------------------------------------------------------------------


class LeadCaptureRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=80, description="Factory slug the lead came from")
    email: str = Field(min_length=5, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)
    # Anti-bot fields
    company_website: Optional[str] = Field(
        default=None,
        description="HONEYPOT — humans never fill this; if set, the lead is rejected.",
        max_length=200,
    )
    dwell_ms: Optional[int] = Field(
        default=None,
        description="Milliseconds between first paint and submit; humans take >3000ms.",
        ge=0,
        le=86_400_000,
    )
    turnstile_token: Optional[str] = Field(
        default=None,
        description="Cloudflare Turnstile token (when widget is on the page).",
        max_length=4000,
    )


class LeadCaptureResponse(BaseModel):
    accepted: bool
    slug: str
    message: str


# ---------------------------------------------------------------------------
# Leads viewer (admin)
# ---------------------------------------------------------------------------


class LeadItem(BaseModel):
    """One stored lead. Emails are masked for any unprivileged caller."""
    slug: str
    email: str  # full email only when caller provides X-Gate-Secret
    name: Optional[str] = None
    ts: int  # unix epoch seconds
    ip_masked: Optional[str] = None  # always masked (last octet hidden)


class LeadsListResponse(BaseModel):
    slug: str
    count: int
    leads: List[LeadItem]
    masked: bool = Field(
        description="True when caller did not provide admin secret; emails partially redacted",
    )


class LeadsStatsBySlug(BaseModel):
    slug: str
    count: int


class LeadsStatsResponse(BaseModel):
    total_leads: int
    by_slug: List[LeadsStatsBySlug]


# ---------------------------------------------------------------------------
# Diagnostics (helps debug CORS / env / version issues from a browser)
# ---------------------------------------------------------------------------


class DiagnosticResponse(BaseModel):
    version: str
    sprint: str
    mode: str  # "live" | "mock"
    cors_allowed_origins: List[str]
    features: Dict[str, bool]
    leads_count_total: int
    runs_count_total: int


# ---------------------------------------------------------------------------
# Admin import (rescue leads stuck in localStorage)
# ---------------------------------------------------------------------------


class LeadImportItem(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=5, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)
    ts_iso: Optional[str] = Field(default=None, description="ISO 8601 timestamp")


class LeadImportRequest(BaseModel):
    leads: List[LeadImportItem] = Field(max_length=500)


class LeadImportResponse(BaseModel):
    imported: int
    skipped_duplicates: int
    by_slug: Dict[str, int]


# ---------------------------------------------------------------------------
# Auth (R27 / ADR-010) — closed beta allowlist
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)


class LoginResponse(BaseModel):
    token: str
    email: str
    expires_at: int  # unix seconds


class MeResponse(BaseModel):
    email: str
    expires_at: int


class LogoutResponse(BaseModel):
    revoked: bool


class AuthAttemptItem(BaseModel):
    email: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    ts: int
    allowed: bool
    reason: str


class AuthAttemptsResponse(BaseModel):
    total: int
    items: List[AuthAttemptItem]


# ---------------------------------------------------------------------------
# Sources + Signals (R28 / ADR-011 — autonomous hunter)
# ---------------------------------------------------------------------------


class SourceCreate(BaseModel):
    kind: str = Field(pattern="^(url|rss|hn|reddit|github_trending|product_hunt|youtube|bluesky|telegram|events|sec_edgar|google_trends)$")
    target: str = Field(default="", max_length=500)
    name: str = Field(min_length=1, max_length=120)


class SourceItem(BaseModel):
    id: int
    kind: str
    target: str
    name: str
    active: bool
    last_scanned_at: Optional[int] = None
    created_at: int


class SourcesListResponse(BaseModel):
    total: int
    items: List[SourceItem]


class SourcesBulkDeleteRequest(BaseModel):
    """M3.16: bulk delete with explicit IDs or filters."""
    source_ids: Optional[List[int]] = Field(default=None, max_length=2000)
    kind_filter: Optional[str] = Field(default=None, description='e.g. "url" to wipe all URL-imports')
    name_contains: Optional[str] = Field(default=None, max_length=200)
    target_contains: Optional[str] = Field(default=None, max_length=200, description='e.g. "instagram.com" or "x.com"')


class SourcesBulkDeleteResponse(BaseModel):
    deleted: int


# ---------------------------------------------------------------------------
# M4.0 — Connected accounts + platform detection (ADR-018)
# ---------------------------------------------------------------------------


class CheckPlatformRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2000)


class CheckPlatformResponse(BaseModel):
    """Result of checking what platform a URL belongs to + credential status."""
    url: str
    platform: Optional[str] = Field(default=None, description='detected platform or null')
    status: str = Field(description='ready | configured | optional_credentials | requires_credentials | deferred | unknown')
    needs_credentials: bool
    missing_keys: List[str] = Field(default_factory=list)
    configured_keys: List[str] = Field(default_factory=list)
    oauth_required: bool = False
    message: str
    recommended_kind: Optional[str] = Field(default=None, description='source kind to register for this URL')
    notes: str = ""


class ConnectedAccountItem(BaseModel):
    platform: str
    status: str
    needs_credentials: bool = False
    missing_keys: List[str] = Field(default_factory=list)
    configured_keys: List[str] = Field(default_factory=list)
    oauth_required: bool = False
    message: str = ""
    recommended_kind: Optional[str] = None
    notes: str = ""
    # Tags from the connected_accounts table (founder-supplied)
    user_notes: Optional[str] = None
    configured_at: Optional[int] = None


class ConnectedAccountsListResponse(BaseModel):
    items: List[ConnectedAccountItem]


class ConnectedAccountUpsertRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=50)
    status: str = Field(pattern='^(configured|deferred|ready|requires_credentials)$')
    notes: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# M4.1 — Preferences + autonomy (ADR-019)
# ---------------------------------------------------------------------------


class PreferencesEngineInfo(BaseModel):
    mode: str = Field(description='"real" if sentence-transformers installed, else "fallback"')
    embedding_lib: Optional[str] = None
    clustering_lib: Optional[str] = None
    embedding_model: Optional[str] = None
    notes: str = ""


class ClusterItem(BaseModel):
    cluster_id: int
    signal_ids: List[int]
    sample_themes: List[str]
    feedback_up: int
    feedback_down: int
    keywords: List[str]


class ClustersResponse(BaseModel):
    total_clusters: int
    mode: str
    items: List[ClusterItem]


class SourceSuggestionItem(BaseModel):
    cluster_id: int
    keywords: List[str]
    suggested_query: str
    rationale: str


class SourceSuggestionsResponse(BaseModel):
    mode: str
    items: List[SourceSuggestionItem]


class AutonomyResponse(BaseModel):
    level: str = Field(description='manual | assisted | autonomous_with_approval')
    updated_at: int


class AutonomyUpdateRequest(BaseModel):
    level: str = Field(pattern='^(manual|assisted|autonomous_with_approval)$')


class ReclusterResponse(BaseModel):
    signals_embedded: int
    clusters_found: int
    mode: str


class SourceQuality(BaseModel):
    source_id: int
    name: str
    kind: str
    signals_total: int
    signals_up: int
    signals_down: int
    signals_promoted: int
    avg_score: float
    quality_score: float


class SourcesQualityResponse(BaseModel):
    items: List[SourceQuality]


class SignalItem(BaseModel):
    id: int
    source_id: Optional[int] = None
    source_kind: str
    source_name: Optional[str] = None  # joined from sources table for nicer UI
    theme: str
    score: float
    excerpt: str
    evidence_urls: List[str]
    suggested_topic: str
    feedback: Optional[str] = None
    promoted_run_id: Optional[str] = None
    trend_score: float = 0
    published_at: Optional[int] = None  # original publication ts of the source content
    analysis: Optional[Dict] = None  # IdeaAnalyzer output (M3.5), null until "Analizar" clicked
    item_titles: List[str] = Field(default_factory=list)  # Parallel to evidence_urls (M3.6)
    # M4.3 — content type classification: news | blog | research_paper |
    # tool_product | course_tutorial | video_podcast | community | corporate | unknown
    content_type: str = Field(default="unknown")
    # M4.4 — language detection + on-demand translation
    language: str = Field(default="unknown", description='Detected: es | en | unknown')
    translated_theme: Optional[str] = None
    translated_excerpt: Optional[str] = None
    created_at: int


class TranslateSignalResponse(BaseModel):
    signal_id: int
    original_language: str
    translated_theme: str
    translated_excerpt: str
    cost_usd_estimated: float = 0.0
    already_in_spanish: bool = False


class SignalsListResponse(BaseModel):
    total: int
    items: List[SignalItem]


class SignalFeedback(BaseModel):
    feedback: str = Field(pattern="^(up|down|clear)$")


class SignalsCleanupResponse(BaseModel):
    deleted: int = Field(description="Number of stale signals removed")
    older_than_days: int = Field(description="Threshold used (days)")
    survivors_kept_with_feedback: int = Field(
        description="Signals older than threshold that were KEPT because they have feedback or promotion",
    )


class SignalsCleanupMocksResponse(BaseModel):
    deleted: int = Field(description="Mock-mode signals removed (theme started with 'Mock signal from')")


# M4.6 — bulk delete by content_type
# M4.6b — extendido para aceptar también source_kind y source_id (opcionales)
class SignalsDeleteByTypeRequest(BaseModel):
    """Acepta cualquier combinación de filtros — al menos uno debe estar
    presente. El endpoint valida que (content_type | source_kind | source_id)
    no sean todos None."""
    content_type: Optional[str] = Field(
        default=None,
        pattern="^(news|blog|research_paper|tool_product|course_tutorial|video_podcast|community|corporate|unknown)$",
        description="Tipo de contenido a borrar (clasificación heurística de M4.3)",
    )
    source_kind: Optional[str] = Field(
        default=None,
        pattern="^(rss|hn|reddit|github_trending|product_hunt|youtube|bluesky|telegram|url|events|sec_edgar|google_trends)$",
        description="Filtra por kind de fuente (M4.6b)",
    )
    source_id: Optional[int] = Field(
        default=None,
        description="Filtra por id puntual de fuente (M4.6b)",
    )
    keep_promoted: bool = Field(
        default=True,
        description="Si True, conserva señales promovidas a un run (historial)",
    )
    keep_feedback: bool = Field(
        default=True,
        description="Si True, conserva señales con 👍/👎 (decisión del founder)",
    )


class SignalsDeleteByTypeResponse(BaseModel):
    deleted: int = Field(description="Cantidad de señales eliminadas")
    content_type: Optional[str] = None
    source_kind: Optional[str] = None
    source_id: Optional[int] = None
    kept_promoted: int = Field(description="Señales del filtro preservadas por estar promovidas")
    kept_feedback: int = Field(description="Señales del filtro preservadas por tener feedback")


# M4.9 — bulk delete por lista de IDs (companion de bulk-feedback)
class SignalsBulkDeleteByIdsRequest(BaseModel):
    signal_ids: List[int] = Field(min_length=1, max_length=500)


class SignalsBulkDeleteByIdsResponse(BaseModel):
    deleted: int


# M4.9 — bulk feedback (multi-select + marcar varias como 👍/👎)
class SignalsBulkFeedbackRequest(BaseModel):
    signal_ids: List[int] = Field(min_length=1, max_length=500, description="IDs a actualizar")
    feedback: str = Field(
        pattern="^(up|down|clear)$",
        description="Feedback a aplicar: 'up' (👍), 'down' (👎), 'clear' (sin marcar)",
    )


class SignalsBulkFeedbackResponse(BaseModel):
    updated: int = Field(description="Cantidad de señales realmente actualizadas")
    feedback_applied: str
    skipped_missing: int = Field(description="IDs que no existen en la base")


# M5.2 — NicheScout
class NicheScoutRequest(BaseModel):
    parent_market: str = Field(min_length=1, max_length=100)
    parent_size: int = Field(ge=1, le=10_000)
    leader_niche: dict
    underexplored_niches: List[dict] = Field(min_length=1, max_length=20)


class NicheScoutResponse(BaseModel):
    target_subniche: str
    entry_thesis: str
    competitive_advantage: str
    minimum_viable_offer: str
    validation_metrics: List[str]
    estimated_capture_pct: str
    key_risks: List[str]
    confidence: float
    reasoning: str
    cost_usd_estimated: float = 0.0
    mock_mode: bool = False


# M5.3 — EventRelevanceScorer
class EventScoringRequest(BaseModel):
    event_title: str = Field(min_length=1, max_length=300)
    event_description: str = Field(default="", max_length=2000)
    evidence_urls: List[str] = Field(default_factory=list, max_length=10)
    industry_focus: str = Field(default="", max_length=200)


class EventScoringResponse(BaseModel):
    relevance_score: float
    expected_attendees_profile: str
    networking_value: str
    learning_value: str
    estimated_cost_usd: str
    expected_roi: str
    recommendation: str  # go | skip | send_someone_else
    preparation_topics: List[str]
    reasoning: str
    cost_usd_estimated: float = 0.0
    mock_mode: bool = False


# M5.4 — SleeperCompanyDetector
class SleeperDetectRequest(BaseModel):
    companies: List[dict] = Field(min_length=1, max_length=20)


class SleeperDetectResponse(BaseModel):
    sector_summary: str
    leader_candidate: str
    sleeper_candidates: List[dict]
    comparison_signals: List[str]
    threat_assessment: str
    investment_thesis: str
    confidence: float
    reasoning: str
    cost_usd_estimated: float = 0.0
    mock_mode: bool = False


# M5.5 — ProductArbitrageEvaluator
class ArbitrageEvalRequest(BaseModel):
    trending_query: str = Field(min_length=1, max_length=300)
    target_geo: str = Field(default="", max_length=10)
    source_cost_usd: Optional[float] = Field(default=None, ge=0, le=100_000)
    target_price_usd: Optional[float] = Field(default=None, ge=0, le=100_000)


class ArbitrageEvalResponse(BaseModel):
    is_physical_product: bool
    product_category: str
    source_region_inferred: str
    target_region_inferred: str
    margin_estimate_pct: str
    shipping_complexity: str
    time_to_test_weeks: str
    key_risks: List[str]
    recommendation: str  # test | skip | deepdive
    confidence: float
    reasoning: str
    cost_usd_estimated: float = 0.0
    mock_mode: bool = False


# M5.0 — TrendGapAnalyzer (agente experimental sobre los gaps de M4.11)
class TrendGapAnalyzeRequest(BaseModel):
    """Body para POST /api/v1/trend-gaps/analyze."""
    idea_summary: str = Field(min_length=1, max_length=500)
    validated_in: List[dict] = Field(
        min_length=1, max_length=20,
        description="Lista de {country, signals, ups, sample_themes} del TrendGapItem",
    )
    missing_in: List[str] = Field(min_length=1, max_length=30)
    opportunity_score: float = Field(default=0.0, ge=0.0, le=1.0)


class TrendGapAnalyzeResponse(BaseModel):
    priority_country: str
    priority_rationale: str
    timing_hypothesis: str
    adoption_pattern: str
    go_to_market: List[str]
    risks_per_country: dict
    effort_estimate_weeks: str
    confidence: float
    reasoning: str
    cost_usd_estimated: float = 0.0
    mock_mode: bool = False


# M4.15 — Niche-en-gigante detector (heurístico Phase 1)
class NicheSubItem(BaseModel):
    topic: str
    signals: int
    sample_themes: List[str] = Field(default_factory=list)


class NicheOpportunity(BaseModel):
    parent_market: str
    parent_size: int
    leader_niche: NicheSubItem
    underexplored_niches: List[NicheSubItem]
    opportunity_count: int


class NicheOpportunitiesResponse(BaseModel):
    total: int
    items: List[NicheOpportunity]


# M4.11 — cross-country trend gaps (first-mover opportunities)
class CountryValidation(BaseModel):
    country: str
    signals: int
    ups: int
    downs: int
    sample_themes: List[str] = Field(default_factory=list)


class TrendGapItem(BaseModel):
    idea_summary: str
    cluster_size: int
    validated_in: List[CountryValidation]
    missing_in: List[str]
    opportunity_score: float


class TrendGapsResponse(BaseModel):
    total: int
    items: List[TrendGapItem]


# M4.7 — distribución de señales por content_type
class SignalsStatsByTypeResponse(BaseModel):
    news: int = 0
    blog: int = 0
    research_paper: int = 0
    tool_product: int = 0
    course_tutorial: int = 0
    video_podcast: int = 0
    community: int = 0
    corporate: int = 0
    unknown: int = 0
    total: int = 0


class SignalAnalysisItem(BaseModel):
    """Output of IdeaAnalyzer — attached to a signal so the founder can
    decide whether to spend $0.06 promoting it to a full workflow run."""
    # M3.11: plain-Spanish summary + main country/region of the idea
    idea_summary: str = Field(default="", description="1-2 sentences in Spanish — what the idea/app actually does")
    country_focus: str = Field(default="", description="Main country or region (Ecuador / LATAM / USA / global / ...)")
    market_size_estimate: str = ""
    icp_probable: str = ""
    competitors: List[str] = Field(default_factory=list)
    differentiator: str = ""
    risks: List[str] = Field(default_factory=list)
    recommendation: str = Field(
        description='"promote" | "wait_for_more_data" | "discard"',
    )
    reasoning: str = ""


class AnalyzeSignalResponse(BaseModel):
    signal_id: int
    analysis: SignalAnalysisItem
    cost_usd_estimated: float = Field(description="LLM cost for this analyze call")


class EnrichSignalResponse(BaseModel):
    """M3.17: result of fetching the signal's URLs and extracting content."""
    signal_id: int
    urls_fetched: int
    urls_failed: int
    theme_updated: bool
    excerpt_updated: bool
    item_titles_updated: bool
    new_theme: Optional[str] = None
    new_excerpt: Optional[str] = None


class AnalyzeSignalsBatchRequest(BaseModel):
    """Pick which signals to analyze. Either explicit IDs, OR auto-pick top N
    not-yet-analyzed signals with at least min_trend trend_score."""
    signal_ids: Optional[List[int]] = Field(default=None, max_length=50)
    top_n: int = Field(default=10, ge=1, le=50, description="Auto-pick: how many to analyze")
    min_trend: int = Field(default=0, ge=0, le=10, description="Auto-pick: minimum trend_score")
    skip_already_analyzed: bool = Field(default=True, description="Skip signals that already have analysis")


class AnalyzeSignalsBatchResponse(BaseModel):
    analyzed: int
    skipped_already_analyzed: int
    errors: int
    cost_usd_estimated: float
    signal_ids_analyzed: List[int]


# M4.10 — Listado de runs recientes para el dashboard de overview
class RunListItem(BaseModel):
    run_id: str
    idea_title: str
    verdict: str  # "pass" | "kill" | "iterate" | "unknown"
    confidence: float
    landing_slug: str
    cost_usd_estimated: float
    needs_human_review: bool
    created_at: int  # epoch seconds; 0 si in-memory mode (sin persistencia)


class RunsListResponse(BaseModel):
    total: int  # cuántos retorna esta página
    items: List[RunListItem]


class StatsResponse(BaseModel):
    """Aggregated counts for sidebar badges + monthly cost indicator."""
    signals_total: int
    signals_new_24h: int           # created in the last 24h
    signals_unmarked: int          # no feedback yet — need triage
    signals_with_analysis: int
    signals_promoted: int
    sources_total: int
    sources_active: int
    runs_total: int
    runs_pending_review: int
    runs_pass: int
    runs_kill: int
    runs_iterate: int
    cost_usd_total_30d: float      # sum of cost_usd_estimated for runs in last 30d
    cost_usd_total_all_time: float


class ScanRunRequest(BaseModel):
    source_ids: Optional[List[int]] = Field(default=None, description="If omitted: scan all active sources")
    auto_promote_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Auto-promote signals with score >= this (0 disables)")
    auto_promote_trend_threshold: int = Field(default=0, ge=0, le=10, description="Auto-promote signals whose trend_score >= this (0 disables) — costs ~$0.06/run, use with caution")
    auto_analyze_trend_threshold: int = Field(default=0, ge=0, le=10, description="Auto-analyze signals whose trend_score >= this (0 disables)")


class ScanRunResponse(BaseModel):
    scanned_sources: int
    items_fetched: int
    signals_created: int
    auto_promoted_runs: List[str]
    signals_auto_analyzed: int = Field(
        default=0,
        description="Signals auto-enriched by IdeaAnalyzer during this scan (only when AUTO_ANALYZE_TREND_THRESHOLD>0)",
    )


class RunFromSourcesRequest(BaseModel):
    """Run the full workflow seeded by either: a topic, a list of URLs,
    or a specific signal_id (which carries its own evidence + suggested_topic)."""
    topic: Optional[str] = Field(default=None, min_length=5, max_length=500)
    urls: Optional[List[str]] = Field(default=None, max_length=10)
    signal_id: Optional[int] = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Links log (R30 / ADR-013) — bitácora de URLs extraídos + analizados
# ---------------------------------------------------------------------------


class LinkLogItem(BaseModel):
    id: int
    url: str
    source_file: Optional[str] = None
    status: str
    idea_summary: Optional[str] = None
    sector: Optional[str] = None
    area: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: int
    analyzed_at: Optional[int] = None


class LinksLogResponse(BaseModel):
    total: int
    by_status: Dict[str, int]
    items: List[LinkLogItem]


class FileImportDiscardedItem(BaseModel):
    """URL descarted by the quality filter (M3.15)."""
    url: str
    reason: str


class FileImportResponse(BaseModel):
    filename: str
    urls_found: int
    urls_added: int
    sources_created: int
    skipped_duplicates: int
    # M3.15 — filtro de calidad
    urls_discarded_as_noise: int = Field(
        default=0,
        description="URLs descartadas por ser ruido (status de X/IG, llamadas, perfiles personales)",
    )
    discarded_samples: List[FileImportDiscardedItem] = Field(
        default_factory=list,
        description="Hasta 10 ejemplos de URLs descartadas con su razón (para transparencia)",
    )


class AnalyzeBatchRequest(BaseModel):
    link_ids: Optional[List[int]] = Field(default=None, max_length=50)
    max_to_analyze: int = Field(default=10, ge=1, le=50)


class AnalyzeBatchResponse(BaseModel):
    analyzed: int
    rejected: int
    errors: int


# ---------------------------------------------------------------------------
# Pipeline view (R30) — runs grouped by phase for the kanban dashboard
# ---------------------------------------------------------------------------


class RunSummary(BaseModel):
    run_id: str
    idea_title: str
    verdict: str
    confidence: float
    landing_slug: str
    needs_human_review: bool
    has_override: bool
    cost_usd_estimated: float
    steps_used: int


class PipelineColumnResponse(BaseModel):
    phase: str
    label: str
    count: int
    runs: List[RunSummary]


class PipelineResponse(BaseModel):
    total_runs: int
    columns: List[PipelineColumnResponse]


# ---------------------------------------------------------------------------
# Response — agent info
# ---------------------------------------------------------------------------


class AgentInfo(BaseModel):
    name: str
    scope_does: str
    scope_does_not: str
    status: str = Field(description='"active" | "deferred"')


class AgentsResponse(BaseModel):
    agents: List[AgentInfo]
    total: int


# ---------------------------------------------------------------------------
# Response — health check
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    mode: str = Field(description='"live" | "mock"')
    workflow: str = "EvidenceGateWorkflow"
    # M3.12 extras for operational visibility (still safe to expose publicly)
    persistent_storage: bool = Field(default=False, description="True if DATABASE_PATH is set (runs/signals survive restart)")
    autoscan_enabled: bool = Field(default=False, description="True if the background scan loop is active")
    server_time: int = Field(default=0, description="Server unix timestamp — useful to detect clock skew")


# ---------------------------------------------------------------------------
# Response — error detail (used in error handlers)
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    detail: str
