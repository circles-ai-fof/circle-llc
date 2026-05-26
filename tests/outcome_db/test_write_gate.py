"""
tests/outcome_db/test_write_gate.py
------------------------------------
Unit tests for OutcomeDBWriteGate.

All tests run without a real database.
Monkey-patching is used for factory operation days.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

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
# Fixtures
# ---------------------------------------------------------------------------

FACTORY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FACTORY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

CLEAN_CONTENT = (
    "Factories in the edtech vertical see highest conversion when "
    "onboarding flow is under 3 steps."
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Clear the in-process factory registry before each test."""
    clear_factory_registry()
    yield
    clear_factory_registry()


@pytest.fixture
def gate_active() -> OutcomeDBWriteGate:
    """Gate with M1 mode OFF (simulates post-activation state)."""
    return OutcomeDBWriteGate(m1_mode=False)


@pytest.fixture
def gate_m1() -> OutcomeDBWriteGate:
    """Gate with M1 mode ON (default Sprint M1 state)."""
    return OutcomeDBWriteGate(m1_mode=True)


def make_insight(
    factory_id: uuid.UUID = FACTORY_A,
    content: str = CLEAN_CONTENT,
    source_data_points: int = 5,
    confidence_level: ConfidenceLevel = ConfidenceLevel.PRELIMINARY,
    tags: list[str] | None = None,
) -> InsightCandidate:
    return InsightCandidate(
        factory_id=factory_id,
        content=content,
        confidence_level=confidence_level,
        source_data_points=source_data_points,
        tags=tags or ["edtech", "onboarding"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidInsightPassesGate:
    def test_valid_insight_passes_gate(self, gate_active: OutcomeDBWriteGate) -> None:
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(source_data_points=5)

        decision = gate_active.validate(insight)

        assert decision.allowed is True
        assert decision.reason == "OK"
        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.factory_id == FACTORY_A

    def test_valid_insight_returns_sanitized_copy(self, gate_active: OutcomeDBWriteGate) -> None:
        register_factory_days(FACTORY_A, 20)
        insight = make_insight(source_data_points=3)

        decision = gate_active.validate(insight)

        # sanitized_insight is a new object, not the same reference
        assert decision.sanitized_insight is not insight
        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.content == insight.content  # clean content unchanged


class TestPIIRejection:
    def test_insight_with_email_is_rejected(self, gate_active: OutcomeDBWriteGate) -> None:
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(
            content="The lead from john.doe@example.com converted after seeing the demo."
        )

        decision = gate_active.validate(insight)

        assert decision.allowed is False
        assert "PII" in decision.reason
        assert decision.sanitized_insight is None

    def test_insight_with_phone_number_is_rejected(self, gate_active: OutcomeDBWriteGate) -> None:
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(
            content="Call +593 99 123 4567 for confirmation of the deal."
        )

        decision = gate_active.validate(insight)

        assert decision.allowed is False
        assert "PII" in decision.reason

    def test_insight_with_cedula_is_rejected(self, gate_active: OutcomeDBWriteGate) -> None:
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(
            content="User with cédula 1712345678 completed the flow."
        )

        decision = gate_active.validate(insight)

        assert decision.allowed is False
        assert "PII" in decision.reason


class TestNewFactoryRejection:
    def test_insight_from_new_factory_is_rejected(self, gate_active: OutcomeDBWriteGate) -> None:
        """Factory with 0 days of operation must be rejected."""
        register_factory_days(FACTORY_A, 0)
        insight = make_insight()

        decision = gate_active.validate(insight)

        assert decision.allowed is False
        assert "0 day(s)" in decision.reason

    def test_insight_from_factory_with_9_days_is_rejected(self, gate_active: OutcomeDBWriteGate) -> None:
        """Boundary: exactly 9 days is still below the 10-day minimum."""
        register_factory_days(FACTORY_A, 9)
        insight = make_insight()

        decision = gate_active.validate(insight)

        assert decision.allowed is False
        assert "9 day(s)" in decision.reason

    def test_insight_from_factory_with_10_days_is_accepted(self, gate_active: OutcomeDBWriteGate) -> None:
        """Boundary: exactly 10 days meets the minimum."""
        register_factory_days(FACTORY_A, 10)
        insight = make_insight()

        decision = gate_active.validate(insight)

        assert decision.allowed is True

    def test_insight_from_unknown_factory_is_rejected(self, gate_active: OutcomeDBWriteGate) -> None:
        """Factory not in registry defaults to 0 days — must be rejected."""
        unknown_factory = uuid.uuid4()
        insight = make_insight(factory_id=unknown_factory)

        decision = gate_active.validate(insight)

        assert decision.allowed is False


class TestConfidenceTagging:
    def test_confidence_tagging_anecdotal(self, gate_active: OutcomeDBWriteGate) -> None:
        """source_data_points=1 → ANECDOTAL regardless of submitted level."""
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(
            source_data_points=1,
            confidence_level=ConfidenceLevel.PREDICTIVE,  # caller submits wrong level
        )

        decision = gate_active.validate(insight)

        assert decision.allowed is True
        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.confidence_level == ConfidenceLevel.ANECDOTAL

    def test_confidence_tagging_preliminary(self, gate_active: OutcomeDBWriteGate) -> None:
        """source_data_points=5 → PRELIMINARY."""
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(source_data_points=5)

        decision = gate_active.validate(insight)

        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.confidence_level == ConfidenceLevel.PRELIMINARY

    def test_confidence_tagging_predictive(self, gate_active: OutcomeDBWriteGate) -> None:
        """source_data_points=10 → PREDICTIVE."""
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(source_data_points=10)

        decision = gate_active.validate(insight)

        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.confidence_level == ConfidenceLevel.PREDICTIVE

    def test_confidence_tagging_correct_boundary(self, gate_active: OutcomeDBWriteGate) -> None:
        """source_data_points=9 → PRELIMINARY (boundary below 10)."""
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(source_data_points=9)

        decision = gate_active.validate(insight)

        assert decision.sanitized_insight is not None
        assert decision.sanitized_insight.confidence_level == ConfidenceLevel.PRELIMINARY


class TestSanitizedInsightHasNoPII:
    def test_sanitized_insight_has_no_pii(self, gate_active: OutcomeDBWriteGate) -> None:
        """After gate passes, sanitized_insight.content must not contain PII."""
        register_factory_days(FACTORY_A, 15)
        # Start with clean content — gate must pass and content must remain clean
        clean = "High-intent users complete onboarding within 2 minutes on average."
        insight = make_insight(content=clean, source_data_points=3)

        decision = gate_active.validate(insight)

        assert decision.allowed is True
        assert decision.sanitized_insight is not None
        # No email, phone, or cédula pattern in output
        assert "@" not in decision.sanitized_insight.content
        assert "[REDACTED]" not in decision.sanitized_insight.content  # nothing was redacted

    def test_gate_rejects_before_returning_sanitized(self, gate_active: OutcomeDBWriteGate) -> None:
        """Rejected insights never have a sanitized_insight populated."""
        register_factory_days(FACTORY_A, 15)
        insight = make_insight(
            content="Contact user@badactor.com for details."
        )

        decision = gate_active.validate(insight)

        assert decision.allowed is False
        assert decision.sanitized_insight is None
