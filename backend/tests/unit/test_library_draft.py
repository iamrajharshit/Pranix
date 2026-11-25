# SPDX-License-Identifier: AGPL-3.0-only
"""D80: `pranix-ctl library draft` writes reviewed-pending deep entries; it never overwrites anything."""

import json
from pathlib import Path
from typing import Any

import pytest

from pranix.config.cli import main
from pranix.ingest import library as intake
from pranix.ingest.kinds import KINDS, NAKSHATRAS, SIGNS
from pranix.llmgw import build
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import Stub
from pranix.util.tokenbucket import TokenBucket

GOOD = {
    "core": "You carry a steady, growing warmth that likes to build things slowly.",
    "gifts": "Patience, a love of beauty and a talent for helping things grow.",
    "growth_edges": "You may hold on to comfort a little long; gentle change can refresh you.",
    "at_work": "You do well with steady, hands-on work where quality is noticed.",
    "in_relationships": "You show love through care, comfort and being reliably there.",
    "practice": "Tend one small growing thing, a plant or a habit, each day this week.",
}


class RecordingStub(Stub):
    """Also keeps the last payload, so the test can check what the AI was given."""

    last_user: str = ""

    def generate(self, system: str, user: str, timeout: float) -> Any:
        self.last_user = user
        return super().generate(system, user, timeout)


def use(monkeypatch: pytest.MonkeyPatch, stub: Stub) -> Stub:
    monkeypatch.setattr(build, "insights_chain", lambda s: Chain([Link(stub, TokenBucket(10_000))]))
    monkeypatch.setenv("PRANIX_ENV", "test")
    return stub


def test_deep_kinds_cover_every_star_sign_and_planet() -> None:
    assert len(NAKSHATRAS) == 27 and len(SIGNS) == 12
    for name, n in (("nakshatra_deep", 27), ("sign_deep", 12), ("planet_deep", 9)):
        assert len(KINDS[name].expected() or []) == n
        assert KINDS[name].fields == ("core", "gifts", "growth_edges", "at_work", "in_relationships", "practice")


def test_draft_writes_drafts_then_the_sheet_loop_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = use(monkeypatch, RecordingStub(reply=GOOD))
    root = tmp_path / "reviewed"
    assert (
        main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--key", "Hasta", "--root", str(root)])
        == 0
    )
    data = intake.load_all(root)["nakshatra_deep"]
    assert list(data) == ["Rohini", "Hasta"] and data["Rohini"]["status"] == "draft"  # star order, not argument order
    assert stub.calls == 2 and intake.verify(root).ok
    payload = json.loads(stub.last_user)  # type: ignore[attr-defined]
    assert payload["facts"]["star"] in ("Rohini", "Hasta") and "library" in payload["facts"]
    # second run: nothing left for these keys, nothing overwritten
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--root", str(root)]) == 0
    assert stub.calls == 2
    out = tmp_path / "sheet.csv"
    assert intake.export_sheet(root, out, ["nakshatra_deep"]) == 2 * 6  # six fields each, ready for review


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ({**GOOD, "core": "It lasts 3 years."}, "NO_NUMERALS"),
        ({**GOOD, "gifts": "Your Venus in Pisces gives charm."}, "UNKNOWN_ENTITY"),
        ({**GOOD, "practice": "x" * 241}, "no valid answer"),
        ({**GOOD, "growth_edges": "A cursed habit."}, "FEAR_LEXICON"),
    ],
)
def test_bad_drafts_are_not_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad: dict[str, str],
    reason: str,
) -> None:
    use(monkeypatch, Stub(reply=bad))
    root = tmp_path / "reviewed"
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--root", str(root)]) == 1
    assert reason in capsys.readouterr().out
    assert intake.load_all(root)["nakshatra_deep"] == {}


def test_add_draft_never_replaces_an_entry(tmp_path: Path) -> None:
    root = tmp_path / "r"
    assert intake.add_draft(root, "planet_deep", "Saturn", GOOD) == []
    again = intake.add_draft(root, "planet_deep", "Saturn", {**GOOD, "core": "Different text."})
    assert [i.rule for i in again] == ["EXISTS"]
    assert intake.load_all(root)["planet_deep"]["Saturn"]["core"] == GOOD["core"]
    assert intake.missing_keys(root, "planet_deep") == [
        "Sun",
        "Moon",
        "Mars",
        "Mercury",
        "Jupiter",
        "Venus",
        "Rahu",
        "Ketu",
    ]


def test_limit_and_no_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = use(monkeypatch, Stub(reply=GOOD))
    root = tmp_path / "r"
    assert main(["library", "draft", "--kind", "sign_deep", "--limit", "2", "--root", str(root)]) == 0
    assert list(intake.load_all(root)["sign_deep"]) == ["Aries", "Taurus"] and stub.calls == 2
    monkeypatch.setattr(build, "insights_chain", lambda s: Chain([]))
    assert main(["library", "draft", "--kind", "sign_deep", "--root", str(root)]) == 1
    assert "no AI provider configured" in capsys.readouterr().out
