# SPDX-License-Identifier: AGPL-3.0-only
"""AI cache keys (F2): meaning-keyed, shared across charts, and retired when the library changes."""

from datetime import date

from pranix.ephemeris.master import compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight.library import Library
from pranix.insight.pipeline import InsightService
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import Fake
from pranix.store.cache import SQLiteCacheStore
from pranix.util.tokenbucket import TokenBucket

M = compute(GOLDEN, date(2026, 11, 14))


def test_ai_text_survives_a_restart_and_needs_no_new_call(tmp_path) -> None:  # type: ignore[no-untyped-def]
    lib = Library(allow_drafts=False)
    first, second = Fake("ok"), Fake("ok")
    a = InsightService(lib, Chain([Link(first, TokenBucket(600))]), cache=SQLiteCacheStore(tmp_path / "c.sqlite"))
    assert a.card("identity", M)["badge"] == "ai" and len(first.payloads) == 1
    b = InsightService(lib, Chain([Link(second, TokenBucket(600))]), cache=SQLiteCacheStore(tmp_path / "c.sqlite"))
    assert b.card("identity", M)["badge"] == "ai" and second.payloads == []


def test_library_version_is_part_of_the_key() -> None:
    approved, drafts = Library(allow_drafts=False), Library(allow_drafts=True)
    assert approved.version != drafts.version and len(approved.version) == 16
    chain = Chain([])
    assert InsightService(approved, chain)._key("identity", M) != InsightService(drafts, chain)._key("identity", M)
    assert InsightService(approved, chain)._key("identity", M) == InsightService(approved, chain)._key("identity", M)
