"""
tests/outcome_db/test_memory_evals.py
--------------------------------------
Memory evals for Outcome DB — Cap 14.5 (AI Builder's Handbook).

These evals validate:
  1. Right memory is retrieved first (retrieval quality)
  2. Write policy captures what matters (relevance filter)
  3. Eviction policy expires anecdotal insights correctly (TTL correctness)

All tests run without a real database or embedding model.
Retrieval is simulated with keyword overlap scoring (proxy for cosine similarity).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

from outcome_db.write_gate import (
    ConfidenceLevel,
    InsightCandidate,
    OutcomeDBWriteGate,
    WriteDecision,
    clear_factory_registry,
    compute_expires_at,
    register_factory_days,
)


# ---------------------------------------------------------------------------
# In-memory retrieval engine (simulates vector similarity with keyword overlap)
# ---------------------------------------------------------------------------

class InMemoryRetrievalEngine:
    """Simulates embedding-based retrieval using token overlap scoring.

    In production this would use pgvector + cosine similarity on 1536-dim embeddings.
    This proxy is sufficient to validate the retrieval contract:
      - The most relevant insight ranks first.
      - Archived/expired insights are excluded.
    """

    def __init__(self) -> None:
        self._insights: List[InsightCandidate] = []
        self._archived: set[uuid.UUID] = set()
        self._expires_at: dict[uuid.UUID, Optional[datetime]] = {}

    def write(
        self,
        insight: InsightCandidate,
        expires_at: Optional[datetime] = None,
    ) -> uuid.UUID:
        doc_id = uuid.uuid4()
        # Store with a synthetic UUID as key by mutating a copy
        # (InsightCandidate uses factory_id as logical key; doc_id is the row key)
        self._insights.append(insight)
        self._expires_at[doc_id] = expires_at
        return doc_id

    def _is_expired(self, insight: InsightCandidate) -> bool:
        """Check TTL against a stored expires_at for the insight content hash."""
        # For test purposes we attach expires_at to the insight's factory_id slot
        # using a side-channel dict keyed by object id
        ea = self._expires_at_by_oid.get(id(insight))
        if ea is None:
            return False
        return ea < datetime.now(tz=timezone.utc)

    def archive(self, insight: InsightCandidate) -> None:
        self._archived.add(id(insight))

    def query(self, query_text: str, top_k: int = 3) -> List[InsightCandidate]:
        """Return top_k insights ranked by token overlap with query_text.

        Excludes archived and expired insights.
        """
        query_tokens = set(query_text.lower().split())
        scored: List[tuple[float, InsightCandidate]] = []

        for insight in self._insights:
            if id(insight) in self._archived:
                continue
            if self._is_expired_by_oid(insight):
                continue
            doc_tokens = set(insight.content.lower().split())
            overlap = len(query_tokens & doc_tokens)
            score = overlap / max(len(query_tokens), 1)
            scored.append((score, insight))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scored[:top_k]]

    # ------------------------------------------------------------------
    # Internal helpers for expires_at tracking by object id
    # ------------------------------------------------------------------
    _expires_at_by_oid: dict[int, datetime] = {}

    def write_with_expiry(
        self,
        insight: InsightCandidate,
        expires_at: Optional[datetime],
    ) -> None:
        self._insights.append(insight)
        if expires_at is not None:
            InMemoryRetrievalEngine._expires_at_by_oid[id(insight)] = expires_at

    def _is_expired_by_oid(self, insight: InsightCandidate) -> bool:
        ea = InMemoryRetrievalEngine._expires_at_by_oid.get(id(insight))
        if ea is None:
            return False
        return ea < datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FACTORY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FACTORY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture(autouse=True)
def reset_registry():
    clear_factory_registry()
    # Also clear the shared class-level dict between tests
    InMemoryRetrievalEngine._expires_at_by_oid.clear()
    yield
    clear_factory_registry()
    InMemoryRetrievalEngine._expires_at_by_oid.clear()


@pytest.fixture
def gate() -> OutcomeDBWriteGate:
    return OutcomeDBWriteGate(m1_mode=False)


@pytest.fixture
def engine() -> InMemoryRetrievalEngine:
    return InMemoryRetrievalEngine()


def make_insight(
    factory_id: uuid.UUID = FACTORY_A,
    content: str = "default insight content",
    source_data_points: int = 5,
    tags: list[str] | None = None,
) -> InsightCandidate:
    return InsightCandidate(
        factory_id=factory_id,
        content=content,
        confidence_level=ConfidenceLevel.PRELIMINARY,
        source_data_points=source_data_points,
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# Eval 1: Right memory retrieved
# ---------------------------------------------------------------------------

class TestRightMemoryRetrieved:
    """Given a query, the most relevant insight must rank first.

    This validates that the retrieval contract is correct regardless
    of the underlying similarity implementation.
    """

    def test_right_memory_retrieved(self, engine: InMemoryRetrievalEngine) -> None:
        """The insight semantically matching the query must be ranked first."""
        insight_pricing = make_insight(
            content="Pricing anchoring at 99 USD per month increases conversion by 18 percent in B2B SaaS.",
            tags=["pricing"],
        )
        insight_onboarding = make_insight(
            content="Async onboarding with video walkthrough reduces drop-off by 30 percent.",
            tags=["onboarding"],
        )
        insight_churn = make_insight(
            content="Churn rate doubles when users miss the activation moment in week one.",
            tags=["churn"],
        )

        engine._insights.extend([insight_pricing, insight_onboarding, insight_churn])

        results = engine.query("pricing conversion B2B month")

        assert len(results) > 0
        assert results[0].tags == ["pricing"], (
            f"Expected pricing insight first, got tags={results[0].tags}"
        )

    def test_onboarding_query_retrieves_onboarding_insight(
        self, engine: InMemoryRetrievalEngine
    ) -> None:
        insight_pricing = make_insight(
            content="Pricing anchoring at 99 USD per month increases conversion.",
            tags=["pricing"],
        )
        insight_onboarding = make_insight(
            content="Async onboarding video walkthrough reduces drop-off significantly.",
            tags=["onboarding"],
        )

        engine._insights.extend([insight_pricing, insight_onboarding])

        results = engine.query("onboarding video drop-off async")

        assert results[0].tags == ["onboarding"]

    def test_archived_insight_excluded_from_retrieval(
        self, engine: InMemoryRetrievalEngine
    ) -> None:
        """Archived insights must not appear in query results."""
        good = make_insight(
            content="Pricing conversion improves with annual plan discount.",
            tags=["pricing"],
        )
        archived = make_insight(
            content="Pricing discount stale insight from old test.",
            tags=["pricing"],
        )

        engine._insights.extend([good, archived])
        engine.archive(archived)

        results = engine.query("pricing discount plan")

        assert archived not in results


# ---------------------------------------------------------------------------
# Eval 2: Write policy captures what matters
# ---------------------------------------------------------------------------

class TestWritePolicyCapturesWhatMatters:
    """High-relevance, clean insights must pass the gate.
    Low-quality or PII-containing insights must be rejected.
    """

    def test_memory_write_policy_captures_what_matters(
        self, gate: OutcomeDBWriteGate
    ) -> None:
        """A high-quality, PII-free insight with ≥10 factory days must pass."""
        register_factory_days(FACTORY_A, 15)

        high_quality = InsightCandidate(
            factory_id=FACTORY_A,
            content=(
                "Factories targeting SMEs in LATAM show 25 percent higher LTV "
                "when onboarding includes a local-language video."
            ),
            confidence_level=ConfidenceLevel.PREDICTIVE,
            source_data_points=12,
            tags=["ltv", "latam", "onboarding"],
            relevance_score=0.95,
        )

        decision = gate.validate(high_quality)

        assert decision.allowed is True
        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.confidence_level == ConfidenceLevel.PREDICTIVE

    def test_low_relevance_insight_structure_is_valid(
        self, gate: OutcomeDBWriteGate
    ) -> None:
        """The gate does not filter by relevance_score (eviction does).
        A low-score but clean insight must still pass the write gate.
        """
        register_factory_days(FACTORY_A, 15)

        low_relevance = InsightCandidate(
            factory_id=FACTORY_A,
            content="Some insight without much detail about user behavior.",
            confidence_level=ConfidenceLevel.ANECDOTAL,
            source_data_points=1,
            tags=["misc"],
            relevance_score=0.1,  # Low score — eviction candidate, but gate allows it
        )

        decision = gate.validate(low_relevance)

        # Gate passes (relevance filtering is eviction's job, not the gate's)
        assert decision.allowed is True

    def test_pii_insight_does_not_pass_even_with_high_relevance(
        self, gate: OutcomeDBWriteGate
    ) -> None:
        """PII must block the insight regardless of relevance_score."""
        register_factory_days(FACTORY_A, 15)

        pii_insight = InsightCandidate(
            factory_id=FACTORY_A,
            content="User admin@startup.com achieved 90 percent activation rate.",
            confidence_level=ConfidenceLevel.PREDICTIVE,
            source_data_points=20,
            tags=["activation"],
            relevance_score=0.99,
        )

        decision = gate.validate(pii_insight)

        assert decision.allowed is False
        assert "PII" in decision.reason


# ---------------------------------------------------------------------------
# Eval 3: Eviction policy expires anecdotal insights
# ---------------------------------------------------------------------------

class TestEvictionPolicyExpiresAnecdotal:
    def test_eviction_policy_expires_anecdotal(
        self, engine: InMemoryRetrievalEngine
    ) -> None:
        """An ANECDOTAL insight with a 90-day TTL must be excluded after expiry."""
        # Simulate an insight whose TTL expired 1 day ago
        expired_time = datetime.now(tz=timezone.utc) - timedelta(days=1)

        expired_insight = make_insight(
            content="Anecdotal pricing observation that should have expired yesterday.",
            tags=["pricing"],
            source_data_points=1,
        )

        engine.write_with_expiry(expired_insight, expires_at=expired_time)

        # Query should return nothing — insight is expired
        results = engine.query("pricing observation anecdotal")

        assert expired_insight not in results

    def test_anecdotal_ttl_is_90_days(self) -> None:
        """compute_expires_at(ANECDOTAL) must return ~90 days from now."""
        now = datetime.now(tz=timezone.utc)
        expires = compute_expires_at(ConfidenceLevel.ANECDOTAL)

        assert expires is not None
        delta = expires - now
        # Allow 1-second tolerance for execution time
        assert 89 * 86400 < delta.total_seconds() <= 90 * 86400 + 1

    def test_preliminary_ttl_is_180_days(self) -> None:
        """compute_expires_at(PRELIMINARY) must return ~180 days from now."""
        now = datetime.now(tz=timezone.utc)
        expires = compute_expires_at(ConfidenceLevel.PRELIMINARY)

        assert expires is not None
        delta = expires - now
        assert 179 * 86400 < delta.total_seconds() <= 180 * 86400 + 1

    def test_predictive_has_no_ttl(self) -> None:
        """compute_expires_at(PREDICTIVE) must return None (no expiry)."""
        expires = compute_expires_at(ConfidenceLevel.PREDICTIVE)

        assert expires is None

    def test_non_expired_anecdotal_is_still_retrievable(
        self, engine: InMemoryRetrievalEngine
    ) -> None:
        """An ANECDOTAL insight with a future TTL must still appear in queries."""
        future_expiry = datetime.now(tz=timezone.utc) + timedelta(days=89)

        fresh_insight = make_insight(
            content="Recent anecdotal pricing insight still within TTL.",
            tags=["pricing"],
            source_data_points=1,
        )

        engine.write_with_expiry(fresh_insight, expires_at=future_expiry)

        results = engine.query("pricing anecdotal recent")

        assert fresh_insight in results

    def test_multiple_ttl_levels_eviction_order(
        self, engine: InMemoryRetrievalEngine
    ) -> None:
        """Expired ANECDOTAL excluded; non-expired PRELIMINARY included."""
        expired_anecdotal = make_insight(
            content="Expired anecdotal observation about pricing.",
            source_data_points=1,
        )
        live_preliminary = make_insight(
            content="Live preliminary observation about pricing trend.",
            source_data_points=5,
        )

        expired_time = datetime.now(tz=timezone.utc) - timedelta(days=91)
        live_time = datetime.now(tz=timezone.utc) + timedelta(days=90)

        engine.write_with_expiry(expired_anecdotal, expires_at=expired_time)
        engine.write_with_expiry(live_preliminary, expires_at=live_time)

        results = engine.query("pricing observation")

        assert expired_anecdotal not in results
        assert live_preliminary in results
