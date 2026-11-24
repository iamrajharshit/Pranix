# SPDX-License-Identifier: AGPL-3.0-only
"""Build the insights chain from configuration (D19, D71, D77, §8.3).

    default: Gemini free models -> Groq -> local model -> (caller) curated library text
    dev:     local model only (offline, zero cost; refused in prod)
    cloud:   Gemini and Groq only

The local model is one `OpenAICompatible` link whatever runs it: Ollama on the PC or llama.cpp on
the Oracle VM. Moving from one to the other changes PRANIX_LOCAL_LLM_URL (and the key), nothing else.
"""

from __future__ import annotations

from ..config.settings import Settings
from ..util.tokenbucket import TokenBucket
from .chain import Chain, Link
from .providers import Fake, Gemini, Groq, OpenAICompatible


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
        links.append(Link(Groq(s.groq_api_key.get_secret_value(), s.groq_model), TokenBucket(s.groq_rpm)))
    return links


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
