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


STARTS = ("Steady", "Bright", "Quiet", "Open", "Warm", "Clear", "Gentle", "Bold", "Patient", "Lively")


class VaryingStub(RecordingStub):
    """Each answer starts its fields with a different word, as a good model would."""

    def generate(self, system: str, user: str, timeout: float) -> Any:
        w = STARTS[self.calls % len(STARTS)]
        self.reply = {f: f"{w} {t[0].lower()}{t[1:]}" for f, t in GOOD.items()}
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
    stub = use(monkeypatch, VaryingStub(reply=GOOD))
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
    stub = use(monkeypatch, VaryingStub(reply=GOOD))
    root = tmp_path / "r"
    assert main(["library", "draft", "--kind", "sign_deep", "--limit", "2", "--root", str(root)]) == 0
    assert list(intake.load_all(root)["sign_deep"]) == ["Aries", "Taurus"] and stub.calls == 2
    monkeypatch.setattr(build, "insights_chain", lambda s: Chain([]))
    assert main(["library", "draft", "--kind", "sign_deep", "--root", str(root)]) == 1
    assert "no AI provider configured" in capsys.readouterr().out


def test_template_voice_is_redrafted_with_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pranix.config.draft_cli import opener, voice_problems

    assert opener("You possess a nature marked by swift beginnings.") == "you possess a"
    assert voice_problems({"core": "You possess a quiet fire."}, {}) == ["core: 'you possess'"]
    assert voice_problems({"at_work": "In your professional life you lead."}, {}) == [
        "at_work: 'in your professional life'"
    ]
    # an opening may be used twice per field, not three times
    assert voice_problems({"gifts": "Patience grows here."}, {"gifts": {"patience grows here": 1}}) == []
    assert voice_problems({"gifts": "Patience grows here."}, {"gifts": {"patience grows here": 2}}) == [
        "gifts starts like 2 other entries: 'patience grows here'"
    ]

    class FirstBadThenGood(RecordingStub):
        def generate(self, system: str, user: str, timeout: float) -> Any:
            self.reply = {**GOOD, "core": "You possess a quiet fire."} if self.calls == 0 else GOOD
            return super().generate(system, user, timeout)

    stub = use(monkeypatch, FirstBadThenGood(reply=GOOD))
    root = tmp_path / "r"
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--root", str(root)]) == 0
    assert stub.calls == 2 and "fix_this" in stub.last_user and "start_with" in stub.last_user
    assert intake.load_all(root)["nakshatra_deep"]["Rohini"]["core"] == GOOD["core"]


def test_openings_are_assigned_least_used_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pranix.config.draft_cli import OPENER_BANK, assign, opener, usage

    fields = KINDS["nakshatra_deep"].fields
    a = assign(fields, usage({}, fields), spread=0)
    b = assign(fields, usage({}, fields), spread=1)
    assert all(a[f] in OPENER_BANK[f] for f in fields) and all(a[f] != b[f] for f in fields)  # neighbours differ
    used = usage({"x": {f: OPENER_BANK[f][0] + " and more." for f in fields}}, fields)
    assert all(assign(fields, used, spread=0)[f] != OPENER_BANK[f][0] for f in fields)  # used ones go last
    assert all(opener(OPENER_BANK[f][0] + " x") in used[f] for f in fields)
    # an opening already used twice is refused
    root = tmp_path / "r"
    v = {f: "Same start here " + t for f, t in GOOD.items()}
    assert intake.add_draft(root, "nakshatra_deep", "Ashwini", v) == []
    assert intake.add_draft(root, "nakshatra_deep", "Bharani", v) == []
    stub = use(monkeypatch, RecordingStub(reply=v))
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Krittika", "--root", str(root)]) == 1
    assert "start_with" in json.loads(stub.last_user) and "Krittika" not in intake.load_all(root)["nakshatra_deep"]


def test_label_prefix_and_healing_are_refused() -> None:
    from pranix.config.draft_cli import OPENER_BANK, voice_problems
    from pranix.ingest import guard

    assert voice_problems({"practice": "Try this: step outside one routine."}, {}) == [
        "practice starts with a label: 'Try this:'"
    ]
    assert not any(o.rstrip().endswith(":") for bank in OPENER_BANK.values() for o in bank)  # bank has no labels
    for word in ("healing", "heal", "heals", "healer"):
        rules = {i.rule for i in guard.check("t", f"You work well in {word} roles.", max_len=240, max_sentences=2)}
        assert "MEDICAL_LEXICON" in rules, word
    assert not guard.check("t", "You restore balance and well-being.", max_len=240, max_sentences=2)
    assert not guard.check("t", "This is for reflection, not health advice.", max_len=240, max_sentences=2)
