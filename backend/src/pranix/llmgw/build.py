# SPDX-License-Identifier: AGPL-3.0-only
"""Build the insights chain from configuration: Gemini models first, then Groq (D19, §8.3)."""

from __future__ import annotations

from ..config.settings import Settings
from ..util.tokenbucket import TokenBucket
from .chain import Chain, Link
from .providers import Gemini, Groq


def insights_chain(s: Settings) -> Chain:
    links: list[Link] = []
    if s.gemini_api_key is not None:
        key = s.gemini_api_key.get_secret_value()
        links += [Link(Gemini(key, m), TokenBucket(s.gemini_rpm)) for m in s.gemini_models]
    if s.groq_api_key is not None:
        links.append(Link(Groq(s.groq_api_key.get_secret_value(), s.groq_model), TokenBucket(s.groq_rpm)))
    return Chain(links)
