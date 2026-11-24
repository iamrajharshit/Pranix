# SPDX-License-Identifier: AGPL-3.0-only
"""Provider adapters. Each returns the model's JSON text for a prompt, or raises ProviderError.

Only the insights chain uses these, and it sends de-identified chart facts only (FR-LLM-18):
no name, pronouns, date, time, place or coordinates ever reach a provider.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class ProviderError(Exception):
    def __init__(self, kind: str, retry_after: float | None = None) -> None:
        super().__init__(kind)
        self.kind, self.retry_after = kind, retry_after  # kind: rate_limited|timeout|http|bad_output|busy


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
class OpenAICompatible:
    """Any server with the OpenAI chat API: Ollama on the PC (`http://localhost:11434/v1`) and the
    llama.cpp server on the Oracle VM (`http://llm:8080/v1`) are the same class with a different URL
    (F5, D77). Moving from local to cloud is a configuration change only.

    `max_concurrent` answers at a time (CPU-only Gemma: 1). A call that finds every slot taken fails
    at once with `busy` instead of queueing, so the chain falls through to the next provider or to
    curated text and nothing waits behind a slow model.
    """

    base_url: str
    model: str
    api_key: str | None = None
    name: str = "local"
    max_concurrent: int = 1
    temperature: float = 0.6
    _slots: threading.BoundedSemaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._slots = threading.BoundedSemaphore(max(1, self.max_concurrent))

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        if not self._slots.acquire(blocking=False):
            raise ProviderError("busy")
        try:
            headers = {"content-type": "application/json"}
            if self.api_key:
                headers["authorization"] = f"Bearer {self.api_key}"
            data = _post(
                f"{self.base_url}/chat/completions",
                headers,
                {
                    "model": self.model,
                    "temperature": self.temperature,
                    "stream": False,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
                timeout,
            )
        finally:
            self._slots.release()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("bad_output") from None
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("bad_output")
        u = data.get("usage") or {}
        return text, Usage(int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)))


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


FAKE_MODES = ("ok", "invalid_json", "numerals", "fear", "unknown_fact", "slow", "rate_limited", "down")


@dataclass
class Fake:
    """Deterministic, free provider for end-to-end, load and failure tests (never in prod).

    ``ok`` echoes the curated draft from the prompt, so it always passes the guardrails; the other
    modes produce one specific failure. Every payload is kept (last 200) so tests can assert that
    no personal data ever reaches a provider.
    """

    mode: str = "ok"
    delay_ms: int = 0
    name: str = "fake"
    model: str = "fake-1"
    payloads: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        with self._lock:
            self.payloads.append(user)
            del self.payloads[:-200]
        wait = self.delay_ms / 1000.0 if self.mode != "slow" else max(self.delay_ms / 1000.0, timeout + 0.05)
        if wait:
            time.sleep(min(wait, timeout))
            if wait > timeout:
                raise ProviderError("timeout")
        if self.mode == "rate_limited":
            raise ProviderError("rate_limited", 30.0)
        if self.mode == "down":
            raise ProviderError("http")
        if self.mode == "invalid_json":
            return "{not json", Usage(10, 3)
        try:
            draft = dict(json.loads(user).get("draft") or {})
        except (ValueError, AttributeError):
            draft = {}
        # the draft is in the structured-reading shape (D80); each failure mode spoils one field
        if "reflect" in draft and not draft["reflect"]:
            draft["reflect"] = "What feels most true for you here?"
        if self.mode == "numerals":
            draft["headline"] = "Your chart in 3 lines"
        elif self.mode == "fear":
            draft["in_short"] = "A cursed placement brings disaster."
        elif self.mode == "unknown_fact":
            draft["fact_ids"] = ["d1.nonexistent.sign"]
            draft["what_it_means"] = str(draft.get("what_it_means", "")) + " {{unknown}}"
        return json.dumps(draft, ensure_ascii=False), Usage(len(user) // 4, 50)
