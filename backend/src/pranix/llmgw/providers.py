# SPDX-License-Identifier: AGPL-3.0-only
"""Provider adapters. Each returns the model's JSON text for a prompt, or raises ProviderError.

Every provider declares the data classes it `accepts` (D82, tasks.py): Gemini's free tier takes
de-identified chart facts only; Groq and our own Gemma also take what a person typed. No name,
pronouns, date, time, place or coordinates ever reach any provider (FR-LLM-18).

`stream()` (chat, V1) yields text pieces as they arrive, for the OpenAI-style providers only.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .tasks import ANY_DATA, FACTS_ONLY


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
    accepts: frozenset[str]

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]: ...


class Streamer(Provider, Protocol):
    def stream(self, system: str, user: str, timeout: float) -> Iterator[str]: ...


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


def _stream(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> Iterator[str]:
    """OpenAI-style server-sent events: `data: {...}` lines, then `data: [DONE]`. Yields content pieces."""
    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=httpx.Timeout(timeout, connect=1.0)) as r:
            if r.status_code == 429:
                raise ProviderError("rate_limited", _retry_after(r))
            if r.status_code >= 400:
                raise ProviderError("http")
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    piece = json.loads(data)["choices"][0].get("delta", {}).get("content")
                except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                    raise ProviderError("bad_output") from None
                if piece:
                    yield str(piece)
    except httpx.TimeoutException:
        raise ProviderError("timeout") from None
    except httpx.HTTPError:
        raise ProviderError("http") from None


def _chat_payload(model: str, temperature: float, system: str, user: str) -> dict[str, Any]:
    """Free text, streamed: no JSON mode (chat answers are prose, checked sentence by sentence in V1)."""
    return {
        "model": model,
        "temperature": temperature,
        "stream": True,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }


@dataclass
class Gemini:
    api_key: str
    model: str
    name: str = "gemini"
    base: str = "https://generativelanguage.googleapis.com/v1beta"
    accepts: frozenset[str] = FACTS_ONLY  # free tier: prompts may improve Google's products (D32)

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
    accepts: frozenset[str] = ANY_DATA  # D77 chat chain; Groq's data terms are a V1 launch gate (D32)

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

    def stream(self, system: str, user: str, timeout: float) -> Iterator[str]:
        headers = {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        yield from _stream(
            f"{self.base}/chat/completions", headers, _chat_payload(self.model, 0.6, system, user), timeout
        )


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
    # 0 = fail fast with "busy" (production: fall through to the next provider). In the offline `dev`
    # chain there is no next provider, so cards wait this many seconds for their turn instead.
    wait_s: float = 0.0
    accepts: frozenset[str] = ANY_DATA  # our own machine: nothing leaves it
    _slots: threading.BoundedSemaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._slots = threading.BoundedSemaphore(max(1, self.max_concurrent))

    def _acquire(self) -> None:
        got = self._slots.acquire(timeout=self.wait_s) if self.wait_s > 0 else self._slots.acquire(blocking=False)
        if not got:
            raise ProviderError("busy")

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        return headers

    def stream(self, system: str, user: str, timeout: float) -> Iterator[str]:
        """Holds the model's slot until the answer ends or the caller stops reading (V1 Stop)."""
        self._acquire()
        try:
            payload = _chat_payload(self.model, self.temperature, system, user)
            yield from _stream(f"{self.base_url}/chat/completions", self._headers(), payload, timeout)
        finally:
            self._slots.release()

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        self._acquire()
        try:
            headers = self._headers()
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
    accepts: frozenset[str] = ANY_DATA
    pieces: tuple[str, ...] = ("Hello", " there.")

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Usage]:
        self.calls += 1
        if self.error:
            raise ProviderError(self.error, 30.0 if self.error == "rate_limited" else None)
        return json.dumps(self.reply or {}), Usage(10, 20)

    def stream(self, system: str, user: str, timeout: float) -> Iterator[str]:
        self.calls += 1
        if self.error:
            raise ProviderError(self.error, 30.0 if self.error == "rate_limited" else None)
        yield from self.pieces


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
    accepts: frozenset[str] = ANY_DATA
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

    def stream(self, system: str, user: str, timeout: float) -> Iterator[str]:
        """Chat double (V1): a calm fixed answer in pieces; `numerals`/`fear` spoil one sentence."""
        with self._lock:
            self.payloads.append(user)
            del self.payloads[:-200]
        if self.mode == "rate_limited":
            raise ProviderError("rate_limited", 30.0)
        if self.mode in ("down", "slow"):
            raise ProviderError("http" if self.mode == "down" else "timeout")
        second = {"numerals": "It lasts 3 years.", "fear": "A cursed placement brings disaster."}.get(
            self.mode, "Notice where it shows up for you."
        )
        for piece in ("This placement asks for patience. ", second):
            if self.delay_ms:
                time.sleep(self.delay_ms / 1000.0)
            yield piece
