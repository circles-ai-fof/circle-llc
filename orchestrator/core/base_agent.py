from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import anthropic

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


class BaseAgent(ABC):
    """
    Single-call agent with Anthropic prompt caching.

    Subclasses implement `system_prompt` and one public method (e.g. generate(), mature()).
    Each public method calls `_call()` for real requests or `_mock_*()` in mock_mode.

    Justification for single-call design: Cap 10 §10.3 — "stay at the simplest level
    that handles 90% of your cases". Each agent in the EvidenceGateWorkflow makes exactly
    one LLM call. No loops, no internal tool use (except landing_generator which is explicit).
    """

    def __init__(
        self,
        client: Optional[anthropic.Anthropic] = None,
        mock_mode: bool = False,
    ) -> None:
        self._mock_mode = mock_mode
        self._client: Optional[anthropic.Anthropic] = (
            None if mock_mode else (client or anthropic.Anthropic())
        )

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @property
    def model(self) -> str:
        return DEFAULT_MODEL

    def _call(self, user_message: str, *, max_tokens: int = 4096) -> str:
        assert self._client is not None, "client required in non-mock mode"
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": self.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def _call_with_tools(
        self,
        user_message: str,
        tools: List[Dict[str, Any]],
        *,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        assert self._client is not None, "client required in non-mock mode"
        return self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": self.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
        )
