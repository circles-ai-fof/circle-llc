"""
tests/outcome_db/test_cross_tenant_isolation.py
------------------------------------------------
Tests for cross-factory isolation rules defined in POLICIES.md §4.

All tests run without a real database.
Isolation is validated at the write_gate + in-memory query simulation level.
The SQL RLS policies are validated by integration tests (out of scope M1).

Reference: AI Builder's Handbook Cap 14 §14.7
"""
from __future__ import annotations

import uuid
from typing import Dict, List

import pytest

from outcome_db.write_gate import (
    ConfidenceLevel,
    InsightCandidate,
    OutcomeDBWriteGate,
    WriteDecision,
    clear_factory_registry,
    register_factory_days,
)


# ---------------------------------------------------------------------------
# In-memory "DB" — simulates RLS filtering without PostgreSQL
# ---------------------------------------------------------------------------

class InMemoryOutcomeDB:
    """Minimal in-memory store that replicates the RLS policy logic:

    SELECT is allowed when:
      factory_id == current_factory_id   (own insights)
      OR cross_vertical == True           (shared insights)
    """

    def __init__(self) -> None:
        self._store: List[InsightCandidate] = []

    def write(self, insight: InsightCandidate) -> None:
        self._store.append(insight)

    def query(self, reader_factory_id: uuid.UUID) -> List[InsightCandidate]:
        """Return insights visible to reader_factory_id (RLS simulation)."""
        return [
            i for i in self._store
            if i.factory_id == reader_factory_id or i.cross_vertical
        ]

    def query_all(self) -> List[InsightCandidate]:
        """Superuser / bypass RLS — never exposed to factory users."""
        return list(self._store)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FACTORY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FACTORY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

CONTENT_A = "Factory A insight: edtech conversion improves with async onboarding."
CONTENT_B = "Factory B insight: fintech activation drops on mobile step 3."
CONTENT_CROSS = "Cross-vertical insight: users churn when first-week activation < 40 pct."


@pytest.fixture(autouse=True)
def reset_registry():
    clear_factory_registry()
    yield
    clear_factory_registry()


@pytest.fixture
def gate() -> OutcomeDBWriteGate:
    return OutcomeDBWriteGate(m1_mode=False)


@pytest.fixture
def db() -> InMemoryOutcomeDB:
    return InMemoryOutcomeDB()


def _write_insight(
    gate: OutcomeDBWriteGate,
    db: InMemoryOutcomeDB,
    factory_id: uuid.UUID,
    content: str,
    cross_vertical: bool = False,
    source_data_points: int = 5,
) -> WriteDecision:
    insight = InsightCandidate(
        factory_id=factory_id,
        content=content,
        confidence_level=ConfidenceLevel.PRELIMINARY,
        source_data_points=source_data_points,
        tags=["test"],
        cross_vertical=cross_vertical,
    )
    decision = gate.validate(insight)
    if decision.allowed and decision.sanitized_insight:
        db.write(decision.sanitized_insight)
    return decision


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFactoryIsolation:
    def test_factory_a_insights_dont_leak_to_factory_b(
        self,
        gate: OutcomeDBWriteGate,
        db: InMemoryOutcomeDB,
    ) -> None:
        """Insights created by Factory A must NOT appear in Factory B queries."""
        register_factory_days(FACTORY_A, 15)
        register_factory_days(FACTORY_B, 20)

        # Write an insight from Factory A (cross_vertical=False)
        dec = _write_insight(gate, db, FACTORY_A, CONTENT_A, cross_vertical=False)
        assert dec.allowed, "Pre-condition: Factory A insight must be written successfully"

        # Query as Factory B
        results_b = db.query(FACTORY_B)

        # Factory A's private insight must NOT appear
        factory_a_ids = {i.factory_id for i in results_b}
        assert FACTORY_A not in factory_a_ids, (
            "Factory A insight leaked to Factory B query"
        )

    def test_factory_b_insights_dont_leak_to_factory_a(
        self,
        gate: OutcomeDBWriteGate,
        db: InMemoryOutcomeDB,
    ) -> None:
        """Symmetrical isolation: B→A."""
        register_factory_days(FACTORY_A, 15)
        register_factory_days(FACTORY_B, 20)

        dec = _write_insight(gate, db, FACTORY_B, CONTENT_B, cross_vertical=False)
        assert dec.allowed

        results_a = db.query(FACTORY_A)
        factory_b_ids = {i.factory_id for i in results_a}
        assert FACTORY_B not in factory_b_ids

    def test_factory_sees_own_insights(
        self,
        gate: OutcomeDBWriteGate,
        db: InMemoryOutcomeDB,
    ) -> None:
        """A factory must be able to query its own insights."""
        register_factory_days(FACTORY_A, 15)

        _write_insight(gate, db, FACTORY_A, CONTENT_A, cross_vertical=False)
        results = db.query(FACTORY_A)

        assert len(results) == 1
        assert results[0].factory_id == FACTORY_A

    def test_cross_vertical_insights_are_visible_to_other_factories(
        self,
        gate: OutcomeDBWriteGate,
        db: InMemoryOutcomeDB,
    ) -> None:
        """cross_vertical=True insights must appear in queries from other factories."""
        register_factory_days(FACTORY_A, 15)

        _write_insight(gate, db, FACTORY_A, CONTENT_CROSS, cross_vertical=True)

        results_b = db.query(FACTORY_B)
        assert len(results_b) == 1
        assert results_b[0].cross_vertical is True

    def test_cross_vertical_false_stays_private(
        self,
        gate: OutcomeDBWriteGate,
        db: InMemoryOutcomeDB,
    ) -> None:
        """cross_vertical=False insight must NOT appear for other factories."""
        register_factory_days(FACTORY_A, 15)

        _write_insight(gate, db, FACTORY_A, CONTENT_A, cross_vertical=False)

        results_b = db.query(FACTORY_B)
        assert len(results_b) == 0

    def test_mixed_store_isolation(
        self,
        gate: OutcomeDBWriteGate,
        db: InMemoryOutcomeDB,
    ) -> None:
        """With multiple insights, each factory sees only its own + cross_vertical."""
        register_factory_days(FACTORY_A, 15)
        register_factory_days(FACTORY_B, 20)

        _write_insight(gate, db, FACTORY_A, CONTENT_A, cross_vertical=False)
        _write_insight(gate, db, FACTORY_B, CONTENT_B, cross_vertical=False)
        _write_insight(gate, db, FACTORY_A, CONTENT_CROSS, cross_vertical=True)

        # Factory A sees: own private + own cross_vertical = 2
        results_a = db.query(FACTORY_A)
        assert len(results_a) == 2

        # Factory B sees: own private + Factory A's cross_vertical = 2
        results_b = db.query(FACTORY_B)
        assert len(results_b) == 2
        # But Factory B's result must NOT include Factory A's private insight
        for r in results_b:
            if r.factory_id == FACTORY_A:
                assert r.cross_vertical is True, (
                    "Factory A private insight leaked to Factory B"
                )


class TestM1WriteLock:
    def test_insights_not_writable_in_m1(self) -> None:
        """In M1 mode all writes must be blocked regardless of other conditions."""
        gate_m1 = OutcomeDBWriteGate(m1_mode=True)
        register_factory_days(FACTORY_A, 99)  # Well above threshold

        insight = InsightCandidate(
            factory_id=FACTORY_A,
            content="A perfectly valid insight with no PII and high quality.",
            confidence_level=ConfidenceLevel.PREDICTIVE,
            source_data_points=20,
            tags=["valid"],
        )

        decision = gate_m1.validate(insight)

        assert decision.allowed is False
        assert "M1_MODE" in decision.reason

    def test_m1_mode_blocks_all_factory_sizes(self) -> None:
        """M1 lock applies regardless of factory maturity."""
        gate_m1 = OutcomeDBWriteGate(m1_mode=True)

        for days in [0, 5, 10, 50, 365]:
            register_factory_days(FACTORY_A, days)
            insight = InsightCandidate(
                factory_id=FACTORY_A,
                content="Valid content without PII — testing M1 lock.",
                confidence_level=ConfidenceLevel.PRELIMINARY,
                source_data_points=5,
                tags=["test"],
            )
            decision = gate_m1.validate(insight)
            assert decision.allowed is False, f"M1 lock failed for factory with {days} days"

    def test_env_variable_controls_m1_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OUTCOME_DB_WRITABLE=false env var must activate M1 mode."""
        monkeypatch.setenv("OUTCOME_DB_WRITABLE", "false")
        gate = OutcomeDBWriteGate()  # reads env var

        register_factory_days(FACTORY_A, 30)
        insight = InsightCandidate(
            factory_id=FACTORY_A,
            content="Valid content without PII for env var test.",
            confidence_level=ConfidenceLevel.PRELIMINARY,
            source_data_points=5,
            tags=["test"],
        )
        decision = gate.validate(insight)
        assert decision.allowed is False
        assert "M1_MODE" in decision.reason

    def test_env_variable_true_allows_writes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OUTCOME_DB_WRITABLE=true must disable M1 mode and allow valid writes."""
        monkeypatch.setenv("OUTCOME_DB_WRITABLE", "true")
        gate = OutcomeDBWriteGate()  # reads env var

        register_factory_days(FACTORY_A, 30)
        insight = InsightCandidate(
            factory_id=FACTORY_A,
            content="Valid content without PII for env var true test.",
            confidence_level=ConfidenceLevel.PRELIMINARY,
            source_data_points=5,
            tags=["test"],
        )
        decision = gate.validate(insight)
        assert decision.allowed is True
