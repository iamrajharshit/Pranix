# SPDX-License-Identifier: AGPL-3.0-only
"""Provider adapters. Each returns the model's JSON text for a prompt, or raises ProviderError.

Only the insights chain uses these, and it sends de-identified chart facts only (FR-LLM-18):
no name, pronouns, date, time, place or coordinates ever reach a provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class ProviderError(Exception):
    def __init__(self, kind: str, retry_after: float | None = None) -> None:
        super().__init__(kind)
        self.kind, self.retry_after = kind, retry_after  # kind: rate_limited|timeout|http|bad_output


@dataclass(frozen=True)
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0


class Provider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]: ...


def _retry_after(r: httpx.Response) -> float | None:
    try:
        return float(r.headers.get("retry-after", ""))
    except ValueError:
        return None


def _post(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=httpx.Timeout(timeout, connect=1.0))
    except httpx.TimeoutException:
        raise ProviderError("timeout") from None
    except httpx.HTTPError:
        raise ProviderError("http") from None
    if r.status_code == 429:
        raise ProviderError("rate_limited", _retry_after(r))
    if r.status_code >= 400:
        raise ProviderError("http")
    data: dict[str, Any] = r.json()
    return data


@dataclass
class Gemini:
    api_key: str
    model: str
    name: str = "gemini"
    base: str = "https://generativelanguage.googleapis.com/v1beta"

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        data = _post(
            f"{self.base}/models/{self.model}:generateContent",
            {"x-goog-api-key": self.api_key, "content-type": "application/json"},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.6},
            },
            timeout,
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("bad_output") from None
        u = data.get("usageMetadata", {})
        return str(text), Usage(int(u.get("promptTokenCount", 0)), int(u.get("candidatesTokenCount", 0)))


@dataclass
class Groq:
    api_key: str
    model: str
    name: str = "groq"
    base: str = "https://api.groq.com/openai/v1"

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        data = _post(
            f"{self.base}/chat/completions",
            {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"},
            {
                "model": self.model,
                "temperature": 0.6,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("bad_output") from None
        u = data.get("usage", {})
        return str(text), Usage(int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)))


@dataclass
class Stub:
    """Test double: returns a fixed JSON reply or raises a given error."""

    reply: dict[str, Any] | None = None
    error: str | None = None
    name: str = "stub"
    model: str = "stub-1"
    calls: int = 0

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        self.calls += 1
        if self.error:
            raise ProviderError(self.error, 30.0 if self.error == "rate_limited" else None)
        return json.dumps(self.reply or {}), Usage(10, 20)
