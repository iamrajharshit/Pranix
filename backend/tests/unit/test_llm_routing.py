# SPDX-License-Identifier: AGPL-3.0-only
"""G1 (D82): AI tasks, the data-class guard, per-task budgets and streaming."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest

from pranix.config.settings import Settings
from pranix.insight import pipeline
from pranix.llmgw import providers
from pranix.llmgw.build import router
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import Fake, Groq, OpenAICompatible, ProviderError, Stub
from pranix.llmgw.tasks import ANY_DATA, FACTS_ONLY, TASKS, RoutingError, Task, check_routing
from pranix.util.tokenbucket import TokenBucket

CHAT, READING = TASKS["veda_chat"], TASKS["card_reading"]
KEYS = {"groq_api_key": "g", "gemini_api_key": "m", "local_llm_url": "http://127.0.0.1:9/v1"}


def link(p: Any, rpm: int = 1000, **kw: Any) -> Link:
    return Link(p, TokenBucket(rpm, clock=lambda: 0.0), **kw)


# ---------- the task registry ----------


def test_tasks_are_declared_once_and_match_the_pipeline() -> None:
    assert set(TASKS) == {"card_reading", "inspect_reading", "veda_answer", "veda_chat"}
    assert READING.prompt_id == pipeline.PROMPT_ID  # one prompt id, so cache keys don't drift
    assert (
        CHAT.data_class == "user_text" and CHAT.chain == "chat" and not CHAT.cacheable
    )  # D18: typed text never cached
    assert all(t.data_class == "facts" and t.chain == "reading" for t in TASKS.values() if t.id != "veda_chat")


# ---------- the guard: typed text never reaches a facts-only provider (D32) ----------


def test_chat_skips_a_facts_only_provider_even_when_it_is_first() -> None:
    gemini_free = Stub(reply={"x": 1}, name="gemini", accepts=FACTS_ONLY)
    groq = Stub(reply={"x": 1}, name="groq")
    chain = Chain([link(gemini_free), link(groq)])
    res = chain.generate("s", "my message", module="chat", task=CHAT)
    assert res is not None and res.provider == "groq" and gemini_free.calls == 0
    assert chain.stream("s", "my message", task=CHAT, module="chat").provider == "groq"  # type: ignore[union-attr]
    assert gemini_free.calls == 0
    assert chain.generate("s", "facts", module="card", task=READING).provider == "gemini"  # type: ignore[union-attr]


def test_a_provider_that_declares_nothing_is_treated_as_facts_only() -> None:
    class Bare:
        name, model = "bare", "b-1"
        calls = 0

        def generate(self, system: str, user: str, timeout: float) -> tuple[str, providers.Usage]:
            self.calls += 1
            return "{}", providers.Usage()

    bare = Bare()
    chain = Chain([link(bare)])
    assert chain.generate("s", "u", module="chat", task=CHAT) is None and bare.calls == 0
    assert chain.generate("s", "u", module="card", task=READING) is not None
    assert check_routing({"reading": Chain([]), "chat": chain})  # and start-up would refuse it


def test_start_up_check_refuses_gemini_free_in_the_chat_chain() -> None:
    gemini = providers.Gemini("k", "gemini-flash-latest")
    problems = check_routing({"reading": Chain([link(gemini)]), "chat": Chain([link(gemini)])})
    assert len(problems) == 1 and "veda_chat" in problems[0] and "gemini" in problems[0]
    assert check_routing({"reading": Chain([]), "chat": Chain([])}) == []  # empty = curated fallback, fine
    assert check_routing({"reading": Chain([])}) == ["task veda_chat: no chain named 'chat'"]


def test_router_builds_safe_chains_for_every_mode() -> None:
    def names(r: Any, chain: str) -> list[str]:
        return [li.provider.name for li in r.chains[chain].links]

    r = router(Settings(env="test", **KEYS))
    assert names(r, "reading") == ["gemini", "gemini", "groq", "gemma"]
    assert names(r, "chat") == ["groq", "gemma"]  # never Gemini free
    assert r.chains["chat"].links[0] is r.chains["reading"].links[2]  # one link: one breaker, one quota
    assert r.chain("veda_chat") is r.chains["chat"] and r.chain("inspect_reading") is r.chains["reading"]
    cloud = router(Settings(env="test", llm_chains="cloud", **KEYS))
    assert names(cloud, "chat") == ["groq"]
    dev = router(Settings(env="test", llm_chains="dev", **KEYS))
    assert names(dev, "reading") == names(dev, "chat") == ["gemma"]
    fake = router(Settings(env="test", llm_fake="ok"))
    assert names(fake, "chat") == ["fake"]
    none = router(Settings(env="test"))
    assert not none.chains["reading"].configured and not none.chains["chat"].configured


def test_router_refuses_an_unsafe_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    from pranix.llmgw import build

    monkeypatch.setattr(build, "Groq", providers.Gemini)  # simulate a bad edit: the chat filter now keeps Gemini
    with pytest.raises(RoutingError, match="veda_chat"):
        router(Settings(env="test", **KEYS))


# ---------- budgets: readings can't use up chat's share of Groq ----------


def test_groq_quota_is_split_between_chat_and_readings() -> None:
    r = router(Settings(env="test", groq_rpm=10, groq_chat_share=0.8, groq_api_key="g"))
    g = r.chains["chat"].links[0]
    assert g.shares["chat"].capacity == 8 and g.shares["reading"].capacity == 2


def test_readings_stop_at_their_share_and_chat_still_gets_through() -> None:
    clock = lambda: 0.0  # noqa: E731
    stub = Stub(reply={"x": 1}, name="groq")
    groq = Link(
        stub,
        TokenBucket(10, clock=clock),
        shares={"chat": TokenBucket(8, clock=clock), "reading": TokenBucket(2, clock=clock)},
    )
    chain = Chain([groq])
    served = [chain.generate("s", "u", module="card", task=READING) for _ in range(4)]
    assert [x is not None for x in served] == [True, True, False, False]  # reading share spent
    assert chain.generate("s", "u", module="chat", task=CHAT) is not None  # chat's share untouched


# ---------- streaming (chat, V1) ----------


def test_stream_falls_through_before_the_first_piece_only() -> None:
    limited = Stub(error="rate_limited", name="groq")
    gemma = Stub(name="gemma", pieces=("Patience ", "helps."))
    chain = Chain([link(limited), link(gemma)])
    s = chain.stream("sys", "u", task=CHAT, module="chat")
    assert s is not None and s.provider == "gemma" and s.depth == 1
    assert "".join(s.pieces) == "Patience helps."
    assert not chain.links[0].breaker.available(0.0)  # the 429 opened the first link's breaker


def test_an_error_after_the_first_piece_reaches_the_caller() -> None:
    class Breaks(Stub):
        def stream(self, system: str, user: str, timeout: float) -> Iterator[str]:
            yield "Half an "
            raise ProviderError("timeout")

    s = Chain([link(Breaks(name="groq")), link(Stub(name="gemma"))]).stream("s", "u", task=CHAT, module="chat")
    assert s is not None and s.provider == "groq"
    with pytest.raises(ProviderError):
        list(s.pieces)  # no silent switch to another voice mid-answer; V1 shows Retry


def test_stream_skips_providers_that_cannot_stream_and_returns_none_when_nobody_can() -> None:
    gemini = providers.Gemini("k", "m", accepts=ANY_DATA)  # even if it accepted typed text, it has no stream()
    assert Chain([link(gemini)]).stream("s", "u", task=CHAT, module="chat") is None
    assert Chain([link(Stub(name="x", pieces=()))]).stream("s", "u", task=CHAT, module="chat") is None


def test_fake_streams_a_calm_answer_and_can_fail_on_purpose() -> None:
    ok = Chain([link(Fake("ok"))]).stream("s", "u", task=CHAT, module="chat")
    assert ok is not None and not any(c.isdigit() for c in "".join(ok.pieces))
    spoiled = Chain([link(Fake("numerals"))]).stream("s", "u", task=CHAT, module="chat")
    assert spoiled is not None and any(c.isdigit() for c in "".join(spoiled.pieces))
    assert Chain([link(Fake("down"))]).stream("s", "u", task=CHAT, module="chat") is None


SSE = (
    b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
    b'data: {"choices":[{"delta":{"content":"Saturn "}}]}\n\n'
    b": keep-alive\n\n"
    b'data: {"choices":[{"delta":{"content":"teaches."}}]}\n\n'
    b"data: [DONE]\n\n"
)


class FakeStream:
    def __init__(self, status: int = 200, body: bytes = SSE, headers: dict[str, str] | None = None) -> None:
        self.status, self.body, self.headers, self.calls = status, body, headers or {}, []  # type: ignore[var-annotated]

    @contextmanager
    def __call__(self, method: str, url: str, **kw: Any) -> Iterator[httpx.Response]:
        self.calls.append({"method": method, "url": url, **kw})
        yield httpx.Response(self.status, content=self.body, headers=self.headers, request=httpx.Request(method, url))


def test_openai_style_stream_is_parsed_and_holds_the_models_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = FakeStream()
    monkeypatch.setattr(providers.httpx, "stream", fs)
    gemma = OpenAICompatible("http://localhost:11434/v1", "gemma4:e2b")
    it = gemma.stream("sys", "u", 30)
    assert next(it) == "Saturn "
    with pytest.raises(ProviderError, match="busy"):  # one answer at a time on a CPU model (D77)
        gemma.generate("s", "u", 5)
    assert list(it) == ["teaches."]
    body = fs.calls[0]["json"]
    assert body["stream"] is True and "response_format" not in body  # prose, not JSON mode
    assert fs.calls[0]["url"] == "http://localhost:11434/v1/chat/completions"


def test_stopping_early_frees_the_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers.httpx, "stream", FakeStream())
    gemma = OpenAICompatible("http://x/v1", "m")
    it = gemma.stream("s", "u", 30)
    next(it)
    it.close()  # the reader pressed Stop
    assert next(gemma.stream("s", "u", 30)) == "Saturn "


def test_groq_stream_errors_map_to_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers.httpx, "stream", FakeStream(429, b"", {"retry-after": "7"}))
    with pytest.raises(ProviderError) as e:
        next(Groq("k", "llama").stream("s", "u", 8))
    assert e.value.kind == "rate_limited" and e.value.retry_after == 7.0
    monkeypatch.setattr(providers.httpx, "stream", FakeStream(200, b"data: {not json}\n\n"))
    with pytest.raises(ProviderError, match="bad_output"):
        next(Groq("k", "llama").stream("s", "u", 8))
    fs = FakeStream()
    monkeypatch.setattr(providers.httpx, "stream", fs)
    assert "".join(Groq("secret", "llama").stream("s", "u", 8)) == "Saturn teaches."
    assert fs.calls[0]["headers"]["authorization"] == "Bearer secret"


def test_custom_task_uses_its_own_timeout() -> None:
    seen: list[float] = []

    class Timed(Stub):
        def generate(self, system: str, user: str, timeout: float) -> tuple[str, providers.Usage]:
            seen.append(timeout)
            return super().generate(system, user, timeout)

    quick = Task("t", "reading", "facts", "p@1", 100, 3.0, True)
    Chain([link(Timed(reply={}))]).generate("s", "u", module="m", task=quick)
    Chain([link(Timed(reply={}), timeout=90.0)]).generate("s", "u", module="m", task=quick)
    assert seen == [3.0, 90.0]  # the local link's own longer timeout still wins
