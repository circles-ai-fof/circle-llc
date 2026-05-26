"""
outcome-db/write_gate.py
------------------------
Write gate for Outcome DB cross-factory insights.

Sprint M1: writable=False by default (R10 rulebook).
This module defines all write-validation logic so it is testable
before the DB is activated.

Reference: AI Builder's Handbook Cap 14 §14.7
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class ConfidenceLevel(str, Enum):
    ANECDOTAL = "anecdotal"      # N = 1
    PRELIMINARY = "preliminary"  # 1 < N < 10
    PREDICTIVE = "predictive"    # N >= 10


class InsightCandidate(BaseModel):
    """Candidate insight submitted for write-gate validation.

    factory_id must be a valid UUID (no sequential integers — prevents
    accidental row-number leakage).
    """

    factory_id: UUID
    content: str = Field(..., min_length=10, max_length=2000)
    confidence_level: ConfidenceLevel
    source_data_points: int = Field(..., ge=1)
    tags: List[str] = Field(default_factory=list)
    cross_vertical: bool = False
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("tags")
    @classmethod
    def tags_non_empty_strings(cls, v: List[str]) -> List[str]:
        cleaned = [t.strip().lower() for t in v if t.strip()]
        return cleaned


class WriteDecision(BaseModel):
    """Result returned by OutcomeDBWriteGate.validate()."""

    allowed: bool
    reason: str
    sanitized_insight: Optional[InsightCandidate] = None


# ---------------------------------------------------------------------------
# PII detection helpers
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[re.Pattern[str]] = [
    # Email addresses
    re.compile(r"\b[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}\b"),
    # International phone numbers (7-15 digits, optional +)
    re.compile(r"(?<!\w)(\+?[0-9]{2,4}[\s\-.]?){2,4}[0-9]{3,4}(?!\w)"),
    # Ecuadorian / LATAM cédula / RUC patterns (10 or 13 digits)
    re.compile(r"\b\d{10}(\d{3})?\b"),
    # Credit card-like patterns (4×4 digits)
    re.compile(r"\b(?:\d[ \-]?){15,16}\b"),
]


def _contains_pii(text: str) -> tuple[bool, str]:
    """Return (True, pattern_name) if PII is detected, else (False, '')."""
    for pattern in _PII_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, f"PII pattern matched: '{pattern.pattern[:40]}...'"
    return False, ""


def _sanitize_content(text: str) -> str:
    """Replace detected PII tokens with [REDACTED].

    This is a best-effort regex pass. Full NER replacement is planned for M6+.
    """
    sanitized = text
    for pattern in _PII_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


# ---------------------------------------------------------------------------
# Factory operation days (injected / retrieved)
# ---------------------------------------------------------------------------

def _get_factory_operation_days(factory_id: UUID) -> int:
    """Return the number of days the factory has been operating.

    In production this calls the factories table.
    In tests this is monkey-patched or injected via dependency.
    """
    # Default: 0 days (safe default — forces rejection for unknown factories)
    return _FACTORY_DAYS_REGISTRY.get(str(factory_id), 0)


# In-process registry for testing / local use.
# Production code replaces this with a DB lookup.
_FACTORY_DAYS_REGISTRY: dict[str, int] = {}


def register_factory_days(factory_id: UUID | str, days: int) -> None:
    """Register operation days for a factory (test helper + local use)."""
    _FACTORY_DAYS_REGISTRY[str(factory_id)] = days


def clear_factory_registry() -> None:
    """Reset the in-process registry (use between tests)."""
    _FACTORY_DAYS_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Confidence auto-tagger
# ---------------------------------------------------------------------------

def _compute_confidence_level(source_data_points: int) -> ConfidenceLevel:
    if source_data_points == 1:
        return ConfidenceLevel.ANECDOTAL
    elif source_data_points < 10:
        return ConfidenceLevel.PRELIMINARY
    else:
        return ConfidenceLevel.PREDICTIVE


# ---------------------------------------------------------------------------
# TTL calculator
# ---------------------------------------------------------------------------

_TTL_DAYS: dict[ConfidenceLevel, Optional[int]] = {
    ConfidenceLevel.ANECDOTAL: 90,
    ConfidenceLevel.PRELIMINARY: 180,
    ConfidenceLevel.PREDICTIVE: None,  # No TTL — quarterly review instead
}


def compute_expires_at(confidence: ConfidenceLevel) -> Optional[datetime]:
    """Return expiry datetime (UTC) or None for PREDICTIVE."""
    ttl = _TTL_DAYS[confidence]
    if ttl is None:
        return None
    return datetime.now(tz=timezone.utc) + timedelta(days=ttl)


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------

class OutcomeDBWriteGate:
    """Validates InsightCandidate objects before writing to outcome-db.

    Usage:
        gate = OutcomeDBWriteGate()
        decision = gate.validate(candidate)
        if decision.allowed:
            db.write(decision.sanitized_insight)
    """

    MIN_OPERATION_DAYS: int = 10

    def __init__(self, m1_mode: Optional[bool] = None) -> None:
        """
        m1_mode: if True, all writes are blocked (Sprint M1 lock).
                 Defaults to env var OUTCOME_DB_WRITABLE != 'true'.
        """
        if m1_mode is not None:
            self._m1_mode = m1_mode
        else:
            writable = os.environ.get("OUTCOME_DB_WRITABLE", "false").lower()
            self._m1_mode = writable != "true"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, insight: InsightCandidate) -> WriteDecision:
        """Run all validation checks and return a WriteDecision.

        Checks (in order):
          1. M1 mode lock
          2. Factory operation days (>= 10)
          3. PII detection in content
          4. Confidence level auto-correction
          5. Schema re-validation of sanitized copy

        Returns WriteDecision with sanitized_insight populated only when
        allowed=True.
        """
        # 1. M1 lock
        if self._m1_mode:
            return WriteDecision(
                allowed=False,
                reason="M1_MODE: outcome-db is inactive until activation criteria are met (POLICIES.md §3)",
            )

        # 2. Factory operation days
        days = _get_factory_operation_days(insight.factory_id)
        if days < self.MIN_OPERATION_DAYS:
            return WriteDecision(
                allowed=False,
                reason=(
                    f"Factory {insight.factory_id} has only {days} day(s) of operation. "
                    f"Minimum required: {self.MIN_OPERATION_DAYS}."
                ),
            )

        # 3. PII detection
        has_pii, pii_reason = _contains_pii(insight.content)
        if has_pii:
            return WriteDecision(
                allowed=False,
                reason=f"Insight content contains PII and was rejected: {pii_reason}",
            )

        # 4. Confidence auto-tag — override caller-supplied level with computed one
        computed_confidence = _compute_confidence_level(insight.source_data_points)

        # 5. Build sanitized copy
        sanitized_content = _sanitize_content(insight.content)

        sanitized = InsightCandidate(
            factory_id=insight.factory_id,
            content=sanitized_content,
            confidence_level=computed_confidence,
            source_data_points=insight.source_data_points,
            tags=insight.tags,
            cross_vertical=insight.cross_vertical,
            relevance_score=insight.relevance_score,
        )

        return WriteDecision(
            allowed=True,
            reason="OK",
            sanitized_insight=sanitized,
        )

    def compute_expires_at(self, confidence: ConfidenceLevel) -> Optional[datetime]:
        """Expose TTL calculation (convenience wrapper for callers)."""
        return compute_expires_at(confidence)
