# SPDX-License-Identifier: AGPL-3.0-only
"""The fake provider (F1): deterministic modes for end-to-end, load and failure tests."""

import json
from datetime import date

import pytest

from pranix.config.settings import Settings
from pranix.ephemeris.master import compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight.library import Library
from pranix.insight.pipeline import InsightService
from pranix.llmgw.build import insights_chain
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import FAKE_MODES, Fake
from pranix.util.tokenbucket import TokenBucket

M = compute(GOLDEN, date(2026, 11, 14))
LIB = Library(allow_drafts=True)


def service(fake: Fake) -> InsightService:
    return InsightService(LIB, Chain([Link(fake, TokenBucket(100_000))]))


def test_ok_mode_echoes_the_draft_and_passes_guardrails() -> None:
    c = service(Fake("ok")).card("identity", M)
    assert c["badge"] == "ai" and c["degraded"] is False


@pytest.mark.parametrize("mode", [m for m in FAKE_MODES if m not in ("ok",)])
def test_every_failure_mode_falls_back_to_curated(mode: str) -> None:
    fake = Fake(mode, delay_ms=0)
    c = service(fake).card("identity", M)
    assert c["badge"] == "curated" and c["degraded"] is True
    assert len(fake.payloads) >= 1


def test_payloads_carry_no_personal_data() -> None:
    fake = Fake("ok")
    svc = service(fake)
    for module in ("identity", "motive", "mind"):
        svc.card(module, M)
    birth = GOLDEN
    banned = {str(birth.lat)[:5], str(birth.lon)[:5], "1984", "Pune", "00:20"}
    for p in fake.payloads:
        json.loads(p)  # well-formed
        assert not any(b in p for b in banned), p[:200]


def test_settings_wire_the_fake_and_prod_refuses_it() -> None:
    chain = insights_chain(Settings(env="test", llm_fake="down"))
    assert chain.configured and chain.links[0].provider.name == "fake"
    assert "llm_fake must be off in prod" in Settings(env="prod", llm_fake="ok").problems()
