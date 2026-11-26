# SPDX-License-Identifier: AGPL-3.0-only
"""Build the AI chains from configuration (D19, D71, D77, D82, §8.3).

Chains by mode (`PRANIX_LLM_CHAINS`):

    mode     reading (facts: cards, Inspector)        chat (typed text: VEDA, V1)
    default  Gemini free -> Groq -> local model       Groq -> local model
    cloud    Gemini free -> Groq                      Groq
    dev      local model only                         local model only

then the caller's own fallback (curated text, prepared answers). `background` (D77) is the local link
alone, for re-wording curated serves later.

Each provider's link is built once and shared by every chain, so its breaker and rate bucket are one.
Groq's quota is split between chat and readings (`groq_chat_share`), so readings can't starve chat.
`router()` checks the routing at start-up: Gemini free can never end up serving typed text (D32).

The local model is one `OpenAICompatible` link whatever runs it: Ollama on the PC or llama.cpp on
the Oracle VM. Moving from one to the other changes PRANIX_LOCAL_LLM_URL (and the key), nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import Settings
from ..util.tokenbucket import TokenBucket
from .chain import Chain, Link
from .providers import Fake, Gemini, Groq, OpenAICompatible
from .tasks import TASKS, RoutingError, check_routing


def local_link(s: Settings) -> Link | None:
    if not s.local_llm_url:
        return None
    key = s.local_llm_api_key.get_secret_value() if s.local_llm_api_key is not None else None
    dev = s.llm_chains == "dev"
    provider = OpenAICompatible(
        s.local_llm_url,
        s.local_llm_model,
        key,
        name="gemma",
        max_concurrent=s.local_llm_concurrency,
        # dev: Gemma is the only AI, so cards queue for it rather than falling back to library text
        wait_s=600.0 if dev else 0.0,
    )
    bucket = TokenBucket(100_000) if dev else TokenBucket(s.local_llm_rpm)  # no rate cap on your own laptop
    return Link(provider, bucket, timeout=s.local_llm_timeout_s)


def cloud_links(s: Settings) -> list[Link]:
    links: list[Link] = []
    if s.gemini_api_key is not None:
        key = s.gemini_api_key.get_secret_value()
        links += [Link(Gemini(key, m), TokenBucket(s.gemini_rpm)) for m in s.gemini_models]
    if s.groq_api_key is not None:
        links.append(groq_link(s))
    return links


def groq_link(s: Settings) -> Link:
    assert s.groq_api_key is not None
    chat = round(s.groq_rpm * s.groq_chat_share)
    shares = {"chat": TokenBucket(max(chat, 1)), "reading": TokenBucket(max(s.groq_rpm - chat, 1))}
    return Link(Groq(s.groq_api_key.get_secret_value(), s.groq_model), TokenBucket(s.groq_rpm), shares=shares)


@dataclass
class Router:
    """The named chains every AI task runs on (tasks.TASKS says which)."""

    chains: dict[str, Chain]
    background: Chain | None

    def chain(self, task_id: str) -> Chain:
        return self.chains[TASKS[task_id].chain]


def router(s: Settings) -> Router:
    reading = insights_chain(s)
    if s.llm_fake != "off":
        chat = Chain(list(reading.links))  # the same fake link
    elif s.llm_chains == "dev":
        chat = Chain(list(reading.links))
    else:  # typed text: Groq, then our own model; never Gemini free (D32)
        chat = Chain([li for li in reading.links if isinstance(li.provider, (Groq, OpenAICompatible))])
    chains = {"reading": reading, "chat": chat}
    problems = check_routing(chains)
    if problems:
        raise RoutingError("; ".join(problems))
    return Router(chains, background_chain(s, reading))


def insights_chain(s: Settings) -> Chain:
    if s.llm_fake != "off":  # tests, end-to-end and load runs only (refused in prod)
        return Chain([Link(Fake(s.llm_fake, s.llm_fake_delay_ms), TokenBucket(100_000))])
    local = local_link(s)
    if s.llm_chains == "dev":
        return Chain([local] if local else [])
    links = cloud_links(s)
    if s.llm_chains == "default" and local:
        links.append(local)
    return Chain(links)


def background_chain(s: Settings, live: Chain) -> Chain | None:
    """The local link of the live chain, shared (same one-slot provider and the same rate bucket), so
    background work never runs a second Gemma call beside a live one or exceeds its rate (D77)."""
    if not s.background_reword or s.llm_fake != "off":
        return None
    for li in live.links:
        if isinstance(li.provider, OpenAICompatible):
            return Chain([Link(li.provider, li.bucket, timeout=li.timeout)])
    return None


def reword_gap_s(s: Settings) -> float:
    """Seconds between background jobs: the local model's own pace."""
    return 60.0 / s.local_llm_rpm


def describe(chain: Chain) -> list[dict[str, str]]:
    """Provider, model and host for logs and `pranix-ctl llm check`; never a key or a path with secrets."""
    out = []
    for li in chain.links:
        p = li.provider
        row = {"provider": p.name, "model": p.model}
        base = getattr(p, "base_url", None) or getattr(p, "base", None)
        if isinstance(base, str):
            row["host"] = base.split("//", 1)[-1].split("/", 1)[0]
        out.append(row)
    return out
