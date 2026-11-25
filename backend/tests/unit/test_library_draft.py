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

GOOD = {  # two sentences per field, no distinctive word in more than two fields (as the tool now requires)
    "core": "You carry a steady warmth that likes to build things slowly. Patience feels natural to you.",
    "gifts": "Beauty and care come easily to you. You help ideas take root and grow.",
    "growth_edges": "You may hold on to comfort a little long. Gentle change can refresh you.",
    "at_work": "You do well with hands-on work where quality is noticed. Careful craft is your strength.",
    "in_relationships": "You show love through comfort and being reliably there. People feel safe near you.",
    "practice": "Tend one small plant or habit each day this week. Notice how little steps add up.",
}


class RecordingStub(Stub):
    """Also keeps the last payload, so the test can check what the AI was given."""

    last_user: str = ""

    def generate(self, system: str, user: str, timeout: float) -> Any:
        self.last_user = user
        self.__dict__.setdefault("users", []).append(user)
        if "rewrite ONE short field" not in system:
            self.__dict__["last_draft_user"] = user
        return super().generate(system, user, timeout)


STARTS = (
    "Calm",
    "Kind",
    "Quiet",
    "Open",
    "Warm",
    "Clear",
    "Brave",
    "Wise",
    "Fair",
    "True",
)  # short: never "distinctive"


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
    payload = json.loads(stub.last_draft_user)  # type: ignore[attr-defined]
    assert payload["facts"]["star"] in ("Rohini", "Hasta") and "library" in payload["facts"]
    # second run: nothing left for these keys, nothing overwritten
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--root", str(root)]) == 0
    assert stub.calls == 2
    out = tmp_path / "sheet.csv"
    assert intake.export_sheet(root, out, ["nakshatra_deep"]) == 2 * 6  # six fields each, ready for review


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ({**GOOD, "core": "It lasts 3 years. You can rest."}, "NO_NUMERALS"),
        ({**GOOD, "gifts": "Your Venus in Pisces gives charm. It shows."}, "UNKNOWN_ENTITY"),
        ({**GOOD, "practice": "x" * 241}, "no valid answer"),
        ({**GOOD, "growth_edges": "A cursed habit. It returns."}, "FEAR_LEXICON"),
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
            self.reply = {**GOOD, "core": "You possess a quiet fire. It glows."} if self.calls == 0 else GOOD
            return super().generate(system, user, timeout)

    stub = use(monkeypatch, FirstBadThenGood(reply=GOOD))
    root = tmp_path / "r"
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--root", str(root)]) == 0
    drafts = [u for u in stub.users if "start_with" in u]  # type: ignore[attr-defined]
    assert len(drafts) == 2 and "fix_this" in drafts[1]
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
    assert "start_with" in json.loads(stub.last_draft_user)  # type: ignore[attr-defined]
    assert "Krittika" not in intake.load_all(root)["nakshatra_deep"]


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


def test_two_word_openings_are_counted_and_phrases_not_reused_across_fields() -> None:
    """Batch 3: "Quietly, you" (two words) was never counted, so it was handed to four stars in a row."""
    from pranix.config import draft_cli as d

    bank = d.OPENER_BANK["core"]
    two = next(o for o in bank if len(d.words(o)) == 2)  # "You embody": a two-word opening
    entries = {k: {"core": f"{two} steady and kind, and more besides."} for k in ("A", "B")}
    used = d.usage(entries, ("core",))
    assert used["core"][" ".join(d.words(two))] == 2
    assert d.assign(("core",), used, spread=0)["core"] != two  # used twice: never assigned again
    assert d.voice_problems({"core": f"{two} warm and bright."}, used)  # and a third use is refused
    assert "quietly, you" not in [o.lower() for o in bank] and "something in you" not in [o.lower() for o in bank]
    assert d.voice_problems({"core": "Quietly, you are defined by grace."}, {}) == ["core: 'you are defined by'"]
    # the same content phrase in two fields of one draft is refused
    clash = {
        "at_work": "You approach tasks with unwavering loyalty.",
        "in_relationships": "You offer unwavering loyalty.",
    }
    assert d.shared_phrases(clash) == ["unwavering loyalty"]
    assert "same phrase in two fields: 'unwavering loyalty'" in d.voice_problems(clash, {})
    assert d.shared_phrases({"a": "You are kind to people.", "b": "You are calm with people."}) == []  # stop words


def test_openings_fit_every_reader_and_anxiety_is_refused() -> None:
    """Batch 4: "When you learn", "At your desk" and "With a partner" assumed a student, a desk job, a partner."""
    from pranix.config import draft_cli as d
    from pranix.ingest import guard

    all_openings = [o.lower() for bank in d.OPENER_BANK.values() for o in bank]
    for narrow in ("when you learn,", "at your desk,", "with a partner, you", "colleagues and teachers notice"):
        assert narrow not in all_openings
    for word in ("anxiety", "anxieties"):
        rules = {i.rule for i in guard.check("t", f"Release your {word} gently.", max_len=240, max_sentences=2)}
        assert "MEDICAL_LEXICON" in rules


def test_a_failing_field_is_reworded_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch 5: Gemma kept writing "Watch for the" after it was used up. Only that field is redone."""
    from pranix.config import draft_cli as d

    class Smart(RecordingStub):
        repairs = 0

        def generate(self, system: str, user: str, timeout: float) -> Any:
            if "rewrite ONE short field" in system:  # the repair prompt
                ask = json.loads(user)
                self.repairs += 1
                self.reply = {"text": f"{ask['begin_with']} keep a calm pace. You finish what you start."}
            else:
                self.reply = {**GOOD, "core": "You possess a quiet warmth. It grows."}  # a banned stem
            return super().generate(system, user, timeout)

    stub = use(monkeypatch, Smart(reply=GOOD))
    root = tmp_path / "r"
    assert main(["library", "draft", "--kind", "nakshatra_deep", "--key", "Rohini", "--root", str(root)]) == 0
    core = intake.load_all(root)["nakshatra_deep"]["Rohini"]["core"]
    assert stub.repairs == 1 and "possess" not in core.lower()
    assert any(core.startswith(o) for o in d.OPENER_BANK["core"])  # begins with an assigned opening
    assert intake.load_all(root)["nakshatra_deep"]["Rohini"]["gifts"] == GOOD["gifts"]  # other fields kept


def test_bad_fields_names_the_later_field_for_a_shared_phrase() -> None:
    from pranix.config.draft_cli import bad_fields

    draft = {
        "at_work": "You bring unwavering loyalty to tasks. Work gets done.",
        "in_relationships": "You offer unwavering loyalty. People feel it.",
    }
    assert list(bad_fields(draft, {})) == ["in_relationships"]


def test_one_sentence_fields_and_overused_words_are_reworded() -> None:
    """Batch 5: fields shrank to one sentence late in the run; "rhythm/rhythmic" appeared in three fields."""
    from pranix.config.draft_cli import bad_fields, overused_words

    assert bad_fields({**GOOD, "core": "You are calm."}, {}) == {"core": "only one sentence: write two"}
    rhythm = {
        **GOOD,
        "core": "You have rhythm and abundance. Groups suit you.",
        "at_work": "You set a rhythmic flow at work. Teams follow it.",
        "in_relationships": "You meet people in a rhythmic way. They feel secure.",
    }
    assert overused_words(rhythm) == ["rhythm"]
    assert bad_fields(rhythm, {}) == {"in_relationships": "same word in too many fields: 'rhythm'"}


def test_sign_and_planet_seeds_use_only_approved_tables() -> None:
    from pranix.config.draft_cli import OPENER_BANK, seed

    libra = seed("sign_deep", "Libra")
    assert libra["element"] == "Air" and libra["ruling_planet"] == "Venus"
    assert libra["exalted_here"] == ["Saturn"] and libra["debilitated_here"] == ["Sun"]
    saturn = seed("planet_deep", "Saturn")
    assert saturn["rules_signs"] == ["Capricorn", "Aquarius"]
    assert saturn["exalted_in"] == "Libra" and saturn["debilitated_in"] == "Aries"
    rahu = seed("planet_deep", "Rahu")  # no dignity table for the nodes, and no empty fields sent
    assert set(rahu) == {"planet", "library"} and all(rahu["library"].values())
    assert not any("star" in o.lower().split() for bank in OPENER_BANK.values() for o in bank)


def test_a_word_twice_in_one_field_is_reworded() -> None:
    """Signs batch 1: "necessary shifts ... necessary evolution", "projects ... projects"."""
    from pranix.config.draft_cli import OPENER_BANK, bad_fields, repeated_within

    assert repeated_within("You resist necessary shifts. Holding on slows necessary evolution.") == ["necess"]
    assert repeated_within("You build steady foundations. People feel safe with you.") == []
    twice = {**GOOD, "at_work": "You handle projects with care. You build structures for teams and projects."}
    assert bad_fields(twice, {}) == {"at_work": "same word twice in one field: 'projec'"}
    openings = [o.lower() for bank in OPENER_BANK.values() for o in bank]
    for gone in ("your way is", "with family and friends,", "for a few minutes"):
        assert gone not in openings


def test_word_worn_across_entries_is_flagged() -> None:
    """Signs batch two: five practices said "observe" — fine one by one, flat as a set (owner review)."""
    from pranix.config.draft_cli import ACROSS_LIMIT, bad_fields, word_usage

    fields = ("practice",)
    have = {k: {"practice": f"Pause and observe your mood, {k}. Then choose one calm step."} for k in "abc"}
    across = word_usage(have, fields)
    assert across["practice"]["observ"] == ACROSS_LIMIT
    worn = {"practice": "Each day, observe your breath for a while. Then return to the task."}
    assert "observ" in bad_fields(worn, {"practice": {}}, across)["practice"]
    fresh = {"practice": "Each day, finish one detail before the next idea. Then rest a moment."}
    assert bad_fields(fresh, {"practice": {}}, across) == {}
    assert bad_fields(worn, {"practice": {}}) == {}  # without the kind's entries, no cross check


def test_template_practice_stems_are_banned() -> None:
    from pranix.config.draft_cli import bad_fields

    got = bad_fields({"practice": "Simply observe your thoughts today. This gentle pause helps you."}, {"practice": {}})
    assert "simply observe" in got["practice"]


def test_theme_words_are_exempt_for_their_own_entry() -> None:
    """The Moon must talk about emotions and feelings; four drafts failed on exactly that (planets batch)."""
    from pranix.config.draft_cli import bad_fields, themes_of

    moon = {
        "core": "Your emotional tides shape how you meet each day. You respond first with feeling.",
        "gifts": "You read emotional currents with ease. Others feel held when you listen.",
        "practice": "When a mood rises, name the emotional weather aloud. Then choose your next step.",
    }
    assert "emotio" in bad_fields(moon, {f: {} for f in moon})["practice"]
    assert bad_fields(moon, {f: {} for f in moon}, theme=themes_of("planet_deep", "Moon")) == {}
    assert themes_of("planet_deep", "Sun") == frozenset()


def test_short_word_deep_counts() -> None:
    from pranix.config.draft_cli import overused_words, word_usage

    draft = {"core": "A deep need guides you. You act.", "gifts": "Deeper meaning calls. You follow.",
             "practice": "Breathe deeply each morning. Then begin."}  # fmt: skip
    assert overused_words(draft) == ["deep"]
    assert word_usage({"a": {"core": "Deep down, you seek. You wait."}}, ("core",))["core"]["deep"] == 1
