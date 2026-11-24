# SPDX-License-Identifier: AGPL-3.0-only
import json
import threading
from typing import Any

import httpx
import pytest

from pranix.config.settings import Settings
from pranix.llmgw import providers
from pranix.llmgw.build import describe, insights_chain
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import OpenAICompatible, ProviderError, Stub
from pranix.util.tokenbucket import TokenBucket


class Recorder:
    def __init__(self, status: int = 200, body: Any = None, delay: threading.Event | None = None) -> None:
        self.status, self.calls = status, []  # type: ignore[var-annotated]
        self.body = (
            body
            if body is not None
            else {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }
        )
        self.gate = delay

    def __call__(self, url: str, headers: dict[str, str], json: dict[str, Any], timeout: Any) -> httpx.Response:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.gate is not None:
            self.gate.wait(5)
        return httpx.Response(self.status, json=self.body, request=httpx.Request("POST", url))


@pytest.fixture
def rec(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    r = Recorder()
    monkeypatch.setattr(providers.httpx, "post", r)
    return r


def test_ollama_style_call_without_key(rec: Recorder) -> None:
    p = OpenAICompatible("http://localhost:11434/v1/", "gemma4:e2b")
    text, usage = p.generate("sys", "user", 30)
    assert text == '{"ok": true}' and usage.tokens_in == 12 and usage.tokens_out == 5
    call = rec.calls[0]
    assert call["url"] == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in call["headers"]
    assert call["json"]["model"] == "gemma4:e2b" and call["json"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in call["json"]["messages"]] == ["system", "user"]


def test_oracle_style_call_sends_the_key(rec: Recorder) -> None:
    OpenAICompatible("http://llm:8080/v1", "gemma", "secret-key").generate("s", "u", 30)
    assert rec.calls[0]["headers"]["authorization"] == "Bearer secret-key"
    assert rec.calls[0]["url"] == "http://llm:8080/v1/chat/completions"


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (429, {}, "rate_limited"),
        (500, {}, "http"),
        (200, {"choices": []}, "bad_output"),
        (200, {"choices": [{"message": {"content": "  "}}]}, "bad_output"),
    ],
)
def test_errors_map_to_provider_errors(monkeypatch: pytest.MonkeyPatch, status: int, body: Any, kind: str) -> None:
    monkeypatch.setattr(providers.httpx, "post", Recorder(status, body))
    with pytest.raises(ProviderError) as e:
        OpenAICompatible("http://x/v1", "m").generate("s", "u", 1)
    assert e.value.kind == kind


def test_one_answer_at_a_time_second_caller_gets_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    monkeypatch.setattr(providers.httpx, "post", Recorder(delay=gate))
    p = OpenAICompatible("http://x/v1", "m", max_concurrent=1)
    t = threading.Thread(target=p.generate, args=("s", "u", 5))
    t.start()
    try:
        for _ in range(200):  # wait until the first call holds the slot
            if p._slots._value == 0:  # type: ignore[attr-defined]
                break
            threading.Event().wait(0.005)
        with pytest.raises(ProviderError) as e:
            p.generate("s", "u", 5)
        assert e.value.kind == "busy"
    finally:
        gate.set()
        t.join()
    p.generate("s", "u", 5)  # the slot is free again


def test_busy_falls_through_without_opening_the_breaker() -> None:
    class Busy(Stub):
        def generate(self, system: str, user: str, timeout: float) -> Any:
            self.calls += 1
            raise ProviderError("busy")

    busy, ok = Busy(name="gemma"), Stub({"a": 1})
    chain = Chain([Link(busy, TokenBucket(100)), Link(ok, TokenBucket(100))])
    for _ in range(5):
        assert chain.generate("s", "u", module="m").provider == "stub"  # type: ignore[union-attr]
    assert chain.links[0].breaker.available(0) and chain.links[0].breaker.failures == 0


def test_per_link_timeout_overrides_the_default() -> None:
    seen: list[float] = []

    class Slow(Stub):
        def generate(self, system: str, user: str, timeout: float) -> Any:
            seen.append(timeout)
            return json.dumps({}), providers.Usage()

    Chain([Link(Slow(), TokenBucket(10), timeout=90.0)]).generate("s", "u", module="m", timeout=8.0)
    Chain([Link(Slow(), TokenBucket(10))]).generate("s", "u", module="m", timeout=8.0)
    assert seen == [90.0, 8.0]


def names(s: Settings) -> list[str]:
    return [li.provider.name for li in insights_chain(s).links]


def test_chains_switch_by_config_only() -> None:
    base = {"env": "test", "gemini_api_key": "g", "groq_api_key": "q", "gemini_models": ["flash"]}
    local = {"local_llm_url": "http://localhost:11434/v1"}
    assert names(Settings(**base)) == ["gemini", "groq"]  # no local model configured
    assert names(Settings(**base, **local)) == ["gemini", "groq", "gemma"]  # local is the last AI link
    assert names(Settings(**base, **local, llm_chains="dev")) == ["gemma"]  # offline
    assert names(Settings(**base, **local, llm_chains="cloud")) == ["gemini", "groq"]
    assert names(Settings(env="test", llm_chains="dev")) == []  # dev without a model: curated text
    # moving from the PC to the Oracle VM: only the URL and key change
    pc = insights_chain(Settings(env="test", llm_chains="dev", **local)).links[0]
    vm = insights_chain(
        Settings(env="test", llm_chains="dev", local_llm_url="http://llm:8080/v1", local_llm_api_key="k")
    ).links[0]
    assert type(pc.provider) is type(vm.provider) is OpenAICompatible
    assert describe(Chain([vm])) == [{"provider": "gemma", "model": "gemma4:e2b", "host": "llm:8080"}]
    assert pc.timeout == 60.0


def test_settings_guard_the_local_model() -> None:
    with pytest.raises(ValueError):
        Settings(env="test", local_llm_url="localhost:11434")
    assert Settings(env="test", local_llm_url="http://h/v1/").local_llm_url == "http://h/v1"
    assert Settings(env="test", local_llm_api_key="").local_llm_api_key is None
    prod = {"env": "prod", "log_pepper": "p" * 40, "chart_key_pepper": "c" * 40}
    assert Settings(**prod).problems() == []
    assert (
        "local_llm_api_key is required in prod when local_llm_url is set"
        in Settings(**prod, local_llm_url="http://llm:8080/v1").problems()
    )
    assert any("llm_chains=dev" in p for p in Settings(**prod, llm_chains="dev").problems())
    assert "local_llm_api_key" in Settings(env="test", local_llm_api_key="k").secret_fingerprints()


def test_fingerprint_never_prints_the_key() -> None:
    fp = Settings(env="test", local_llm_api_key="very-secret").secret_fingerprints()["local_llm_api_key"]
    assert "very-secret" not in fp and len(fp) == 6


def test_cli_check_and_bench_with_the_fake_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pranix.config.cli import main

    monkeypatch.setenv("PRANIX_ENV", "test")
    monkeypatch.setenv("PRANIX_LLM_FAKE", "ok")
    assert main(["llm", "check"]) == 0
    assert main(["llm", "bench", "--rounds", "1"]) == 0
    out = capsys.readouterr().out
    assert "fake-1" in out and "13/13" in out
    monkeypatch.setenv("PRANIX_LLM_FAKE", "down")
    assert main(["llm", "check"]) == 1
