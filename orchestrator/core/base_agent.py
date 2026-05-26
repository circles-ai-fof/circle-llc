from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import anthropic

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# ---------------------------------------------------------------------------
# Langfuse observability — opt-in via LANGFUSE_PUBLIC_KEY env var.
# If the package is missing or the key is unset the agents work unchanged.
# ---------------------------------------------------------------------------
try:
    from langfuse import Langfuse as _Langfuse  # noqa: F401 — imported for availability check
    _LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
    if _LANGFUSE_ENABLED:
        _langfuse_client = _Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    else:
        _langfuse_client = None
except ImportError:
    _LANGFUSE_ENABLED = False
    _langfuse_client = None


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
        output_text = response.content[0].text

        # --- Langfuse tracing (opt-in, never breaks the agent) ---
        if _LANGFUSE_ENABLED and _langfuse_client is not None:
            try:
                usage = response.usage
                _langfuse_client.generation(
                    name=f"{self.__class__.__name__}._call",
                    model=self.model,
                    input=user_message,
                    output=output_text,
                    usage={
                        "input": usage.input_tokens,
                        "output": usage.output_tokens,
                    },
                    metadata={"agent": self.__class__.__name__},
                )
            except Exception:  # noqa: BLE001 — observability must never crash the agent
                pass

        return output_text

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """
        Robustly extract a JSON object from LLM output.
        Handles: raw JSON, ```json fences, leading/trailing prose.
        Raises ValueError if no valid JSON object is found.
        """
        # 1. Direct parse
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass
        # 2. Strip ```json ... ``` fences
        fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass
        # 3. Find first { ... } block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"No valid JSON object found in LLM output: {raw[:200]!r}")

    def _call_with_tools(
        self,
        user_message: str,
        tools: List[Dict[str, Any]],
        *,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
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
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
        )

        # --- Langfuse tracing (opt-in, never breaks the agent) ---
        if _LANGFUSE_ENABLED and _langfuse_client is not None:
            try:
                usage = response.usage
                # Summarise tool calls for the output field
                tool_calls = [
                    {"name": b.name, "input": b.input}
                    for b in response.content
                    if b.type == "tool_use"
                ]
                _langfuse_client.generation(
                    name=f"{self.__class__.__name__}._call_with_tools",
                    model=self.model,
                    input=user_message,
                    output=tool_calls or [b.text for b in response.content if b.type == "text"],
                    usage={
                        "input": usage.input_tokens,
                        "output": usage.output_tokens,
                    },
                    metadata={
                        "agent": self.__class__.__name__,
                        "tool_count": len(tools),
                        "tool_calls_made": len(tool_calls),
                    },
                )
            except Exception:  # noqa: BLE001 — observability must never crash the agent
                pass

        return response
