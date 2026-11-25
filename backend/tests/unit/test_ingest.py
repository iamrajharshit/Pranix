# SPDX-License-Identifier: AGPL-3.0-only
import csv
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pranix.config.cli import main
from pranix.ingest import guard, library, rules, sheet, yamlio
from pranix.ingest.kinds import KINDS

OK_TEXT = "Growth comes through how you show up and take your place."


def seed(root: Path, files: dict[str, dict]) -> None:  # type: ignore[type-arg]
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (root / f"{name}.yaml").write_text(yamlio.dump(data), encoding="utf-8")


def entry(text: str = OK_TEXT, status: str = "draft") -> dict[str, str]:
    return {"status": status, "text": text}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "inspect"
    seed(r, {
        "planet_in_house": {
            "Jupiter": {"house_1": entry(), "house_2": entry("Wealth grows through generosity and learning."), "house_3": entry("Courage grows through small brave steps.", "approved")},
            "Moon": {"house_4": entry("Feelings feel at home and settled here.")},
        },
        "houses": {"house_1": {"status": "draft", "arena": "Self and first impressions.", "healthy": "Showing up as yourself.", "growth": "Learning to take space kindly."}},
        "signals": {"vargottama": entry("The same sign in both charts adds steadiness.")},
    })  # fmt: skip
    return r


def make_sheet(path: Path, rows: list[dict[str, str]]) -> Path:
    cols = ("key", "field", "draft", "decision", "edited", "note")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return path


def row(key: str, draft: str, decision: str, edited: str = "", field: str = "text", note: str = "") -> dict[str, str]:
    return {"key": key, "field": field, "draft": draft, "decision": decision, "edited": edited, "note": note}


# ---------- canonical YAML ----------


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=80))
def test_yaml_round_trip_any_text(text: str) -> None:
    data = {"a": {"k": {"status": "draft", "text": text}}, "list": [1, 2, 3]}
    assert yamlio.load(yamlio.dump(data)) == data


def test_yaml_is_byte_stable_and_keeps_order() -> None:
    data = {"b": {"status": "draft", "text": "x"}, "a": {"status": "approved", "text": "y"}}
    assert yamlio.dump(data) == yamlio.dump(dict(data))
    assert yamlio.dump(data).index("\nb:") < yamlio.dump(data).index("\na:")
    assert yamlio.dump({"yes": {"status": "draft", "text": "x"}}).count('"yes"') == 1  # YAML 1.1 booleans stay strings


# ---------- guardrails ----------


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("", "EMPTY"),
        ("Seven houses ahead, you grow 7 times.", "NO_NUMERALS"),
        ("A maraka house brings pressure.", "BANNED_LABEL"),
        ("The Guru-Chandal yoga is heavy.", "BANNED_LABEL"),
        ("This is a TODO line.", "PLACEHOLDER"),
        ("Growth comes through [something].", "PLACEHOLDER"),
        ("You will definitely meet a partner.", "PREDICTION"),
        ("This is a disaster for you.", "FEAR_LEXICON"),
        ("It helps with a disorder.", "MEDICAL_LEXICON"),
        ("{{name}}, you grow here.", "TEMPLATE_TOKEN"),
        ("One. Two. Three sentences here.", "TOO_MANY_SENTENCES"),
        ("No full stop at the end", "END_PUNCTUATION"),
        ("Two  spaces inside.", "WHITESPACE"),
        ("x" * 300 + ".", "TOO_LONG"),
    ],
)
def test_guard_catches_each_rule(text: str, rule: str) -> None:
    assert rule in {i.rule for i in guard.check("t", text, max_len=240, max_sentences=2)}


def test_guard_allows_chart_names_and_clean_text() -> None:
    assert (
        guard.check("t", "Your D9 chart shows the same sign, which adds steadiness.", max_len=240, max_sentences=2)
        == []
    )


# ---------- library: export, import, verify ----------


def test_export_lists_only_drafts_unless_all(root: Path, tmp_path: Path) -> None:
    n = library.export_sheet(root, tmp_path / "s.csv")
    assert n == 3 + 3 + 1  # three planet drafts, the house's three fields, one signal
    assert library.export_sheet(root, tmp_path / "all.csv", include_all=True) == n + 1
    assert library.export_sheet(root, tmp_path / "k.csv", kinds=["signals"]) == 1


def test_full_loop_approve_edit_reject_hold(root: Path, tmp_path: Path) -> None:
    sh = make_sheet(tmp_path / "s.csv", [
        row("planet_in_house/Jupiter/house_1", OK_TEXT, "approve"),
        row("planet_in_house/Jupiter/house_2", "Wealth grows through generosity and learning.", "edit", "Resources grow through generosity and learning."),
        row("planet_in_house/Moon/house_4", "Feelings feel at home and settled here.", "reject", note="too vague"),
        row("signals/vargottama", "The same sign in both charts adds steadiness.", "hold"),
    ])  # fmt: skip
    before = (root / "planet_in_house.yaml").read_bytes()
    dry = library.import_sheet(root, sh)
    assert dry.ok and not dry.written and (root / "planet_in_house.yaml").read_bytes() == before  # dry run
    rep = library.import_sheet(root, sh, write=True)
    assert rep.ok and rep.written
    data = library.load_all(root)
    pih = data["planet_in_house"]
    assert pih["Jupiter"]["house_1"]["status"] == "approved"
    assert pih["Jupiter"]["house_2"] == {
        "status": "approved",
        "text": "Resources grow through generosity and learning.",
    }
    assert pih["Moon"]["house_4"]["status"] == "draft"
    assert rep.held == ["signals/vargottama"]
    assert [c.decision for c in rep.changes] == ["approve", "edit", "reject"]
    assert "was: Wealth grows" in rep.markdown() and "now: Resources grow" in rep.markdown()
    assert library.verify(root).ok


def test_import_is_deterministic(root: Path, tmp_path: Path) -> None:
    sh = make_sheet(tmp_path / "s.csv", [row("planet_in_house/Jupiter/house_1", OK_TEXT, "approve")])
    import shutil

    other = tmp_path / "copy"
    shutil.copytree(root, other)
    a = library.import_sheet(root, sh, write=True)
    b = library.import_sheet(other, sh, write=True)
    assert a.content_hash == b.content_hash
    for p in root.iterdir():
        assert p.read_bytes() == (other / p.name).read_bytes()


def test_manifest_hash_changes_with_content(root: Path, tmp_path: Path) -> None:
    sh1 = make_sheet(tmp_path / "a.csv", [row("planet_in_house/Jupiter/house_1", OK_TEXT, "approve")])
    h1 = library.import_sheet(root, sh1, write=True).content_hash
    sh2 = make_sheet(
        tmp_path / "b.csv",
        [row("planet_in_house/Jupiter/house_2", "Wealth grows through generosity and learning.", "approve")],
    )
    h2 = library.import_sheet(root, sh2, write=True).content_hash
    assert h1 != h2
    assert json.loads((root / "manifest.json").read_text())["content_hash"] == h2


def _errors(root: Path, tmp_path: Path, rows: list[dict[str, str]]) -> set[str]:
    rep = library.import_sheet(root, make_sheet(tmp_path / "e.csv", rows))
    assert not rep.ok
    return {e.rule for e in rep.errors}


def test_all_or_nothing_when_any_row_fails(root: Path, tmp_path: Path) -> None:
    sh = make_sheet(tmp_path / "s.csv", [
        row("planet_in_house/Jupiter/house_1", OK_TEXT, "approve"),
        row("planet_in_house/Jupiter/house_2", "Wealth grows through generosity and learning.", "edit", "Grow by 3 steps."),
    ])  # fmt: skip
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    rep = library.import_sheet(root, sh, write=True)
    assert not rep.ok and "NO_NUMERALS" in {e.rule for e in rep.errors} and not rep.written
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


def test_sheet_errors(root: Path, tmp_path: Path) -> None:
    j1 = "planet_in_house/Jupiter/house_1"
    assert "STALE_SHEET" in _errors(root, tmp_path, [row(j1, "Old text that changed.", "approve")])
    assert "UNKNOWN_KEY" in _errors(root, tmp_path, [row("planet_in_house/Jupiter/house_9", OK_TEXT, "approve")])
    assert "UNKNOWN_KEY" in _errors(root, tmp_path, [row("planet_in_house/Pluto/house_1", OK_TEXT, "approve")])
    assert "UNKNOWN_KIND" in _errors(root, tmp_path, [row("nope/x", OK_TEXT, "approve")])
    assert "UNKNOWN_FIELD" in _errors(root, tmp_path, [row(j1, OK_TEXT, "approve", field="body")])
    assert "BAD_DECISION" in _errors(root, tmp_path, [row(j1, OK_TEXT, "maybe")])
    assert "EDIT_WITH_APPROVE" in _errors(root, tmp_path, [row(j1, OK_TEXT, "approve", "Something else.")])
    assert "EDIT_EMPTY" in _errors(root, tmp_path, [row(j1, OK_TEXT, "edit")])
    assert "DUPLICATE_ROW" in _errors(root, tmp_path, [row(j1, OK_TEXT, "approve"), row(j1, OK_TEXT, "approve")])


def test_multi_field_entries_decide_per_field_and_need_all_fields(root: Path, tmp_path: Path) -> None:
    k = "houses/house_1"
    a, h, g = "Self and first impressions.", "Showing up as yourself.", "Learning to take space kindly."
    rows = [
        row(k, a, "approve", field="arena"),
        row(k, h, "approve", field="healthy"),
        row(k, g, "approve", field="growth"),
    ]
    assert "MISSING_FIELD_ROW" in _errors(root, tmp_path, rows[:2])
    # approve + edit on one entry: edits applied, entry goes live (owner reviews field by field)
    mixed = [rows[0], {**rows[1], "decision": "Edit", "edited": "Being yourself, kindly."}, rows[2]]
    rep = library.import_sheet(root, make_sheet(tmp_path / "mixed.csv", mixed))
    assert rep.ok and [c.decision for c in rep.changes] == ["edit"]
    # any reject: edits kept, entry stays draft
    rejecting = [rows[0], {**rows[1], "decision": "edit", "edited": "Being yourself, kindly."},
                 {**rows[2], "decision": "reject"}]  # fmt: skip
    rep = library.import_sheet(root, make_sheet(tmp_path / "rej.csv", rejecting), write=True)
    assert rep.ok and [c.decision for c in rep.changes] == ["reject"]
    h1 = library.load_all(root)["houses"]["house_1"]
    assert h1["status"] == "draft" and h1["healthy"] == "Being yourself, kindly."
    # a field-level mistake is reported against that field
    oops = [rows[0], {**rows[1], "decision": "edit"}, rows[2]]
    assert "EDIT_EMPTY" in _errors(root, tmp_path, [{**r, "draft": h1[r["field"]]} for r in oops])
    rep = library.import_sheet(
        root, make_sheet(tmp_path / "ok.csv", [{**r, "draft": h1[r["field"]]} for r in rows]), write=True
    )
    assert rep.ok and library.load_all(root)["houses"]["house_1"]["status"] == "approved"


def test_excel_round_trip_whitespace_is_not_a_stale_sheet(root: Path, tmp_path: Path) -> None:
    sh = make_sheet(
        tmp_path / "s.csv", [row("planet_in_house/Jupiter/house_1", "  " + OK_TEXT.replace(" ", "  ") + " ", "approve")]
    )
    assert library.import_sheet(root, sh).ok


def test_sheet_formats_and_bad_files(root: Path, tmp_path: Path) -> None:
    tsv = tmp_path / "s.tsv"  # a tab-separated paste from a spreadsheet works too
    tsv.write_text(
        f"Key\tField\tDraft\tDecision\nplanet_in_house/Jupiter/house_1\ttext\t{OK_TEXT}\t✅\n", encoding="utf-8"
    )
    assert library.import_sheet(root, tsv).changes[0].decision == "approve"
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    rep = library.import_sheet(root, bad)
    assert [e.rule for e in rep.errors] == ["BAD_SHEET"]


def test_verify_catches_edits_made_outside_the_importer(root: Path, tmp_path: Path) -> None:
    library.import_sheet(
        root, make_sheet(tmp_path / "s.csv", [row("planet_in_house/Jupiter/house_1", OK_TEXT, "approve")]), write=True
    )
    assert library.verify(root).ok
    p = root / "planet_in_house.yaml"
    p.write_text(p.read_text().replace("take your place", "take up room"), encoding="utf-8")
    assert "MANIFEST_STALE" in {e.rule for e in library.verify(root).errors}
    (root / "manifest.json").unlink()
    assert "MANIFEST_MISSING" in {e.rule for e in library.verify(root).errors}


def test_verify_flags_bad_entries_in_any_status(tmp_path: Path) -> None:
    r = tmp_path / "v"
    seed(
        r,
        {
            "planet_in_house": {
                "Sun": {"house_1": entry("It lasts 3 years."), "house_20": entry()},
                "Pluto": {"house_1": entry()},
            }
        },
    )
    rules_hit = {e.rule for e in library.verify(r).errors}
    assert {"NO_NUMERALS", "INVALID_KEY", "MANIFEST_MISSING"} <= rules_hit


def test_coverage_counts_expected_keys(root: Path) -> None:
    cov = library.verify(root).coverage
    assert (
        cov["planet_in_house"]["expected"] == 108
        and cov["planet_in_house"]["approved"] == 1
        and cov["planet_in_house"]["draft"] == 3
    )
    assert cov["planet_in_house"]["missing"] == 104
    assert cov["lord_in_house"]["expected"] == 144 and cov["houses"]["expected"] == 12
    assert cov["signals"]["expected"] is None


def test_packaged_library_verifies() -> None:
    assert library.verify(library.default_root()).ok  # no reviewed files yet, or all clean once they land
    assert set(KINDS) == {"houses", "planet_in_house", "lord_in_house", "signals", "bridge",
                          "nakshatra_deep", "sign_deep", "planet_deep"}  # fmt: skip


# ---------- rules ----------


def rsheet(path: Path, rows: list[tuple[str, str, str, str, str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["table", "key", "value", "decision", "edited", "note"])
        for t, k, v, d, e in rows:
            w.writerow([t, k, v, d, e, ""])
    return path


def test_rules_import_and_rewrite(tmp_path: Path) -> None:
    target = tmp_path / "jyotish-core@1.yaml"
    sh = rsheet(tmp_path / "r.csv", [
        ("graha_drishti", "Jupiter", "5,7,9", "approve", ""),
        ("graha_drishti", "Rahu", "5;7;9", "approve", ""),  # D72
        ("graha_drishti", "Mars", "4,7,8", "approve", ""),
        ("natural_nature", "Moon", "conditional", "approve", ""),
        ("house_categories", "house_1", "kendra,trikona", "approve", ""),
        ("signal_priority", "vargottama", "80", "approve", ""),
        ("signal_priority", "debilitated", "70", "approve", ""),
        ("suppression", "vargottama", "debilitated", "approve", ""),
        ("natural_nature", "Sun", "malefic", "hold", ""),
    ])  # fmt: skip
    rep = rules.import_sheet(target, sh, "2026-11-28", write=True)
    assert rep.ok and rep.written and len(rep.added) == 8 and rep.skipped == ["natural_nature/Sun"]
    doc = yamlio.load(target.read_text())
    assert doc["tables"]["graha_drishti"]["Rahu"] == [5, 7, 9]
    assert doc["reviewed_at"] == "2026-11-28" and doc["status"] == "PARTIAL"
    assert list(doc["tables"]["graha_drishti"]) == ["Mars", "Jupiter", "Rahu"]  # planet order, not sheet order
    # a second sheet edits one value: shows in the report as changed
    sh2 = rsheet(tmp_path / "r2.csv", [("graha_drishti", "Mars", "4,7,8", "edit", "4, 7, 8, 12")])
    rep2 = rules.import_sheet(target, sh2, write=True)
    assert rep2.changed == [("graha_drishti/Mars", [4, 7, 8], [4, 7, 8, 12])]
    assert rules.verify(target).ok
    out = tmp_path / "back.csv"
    assert rules.export_sheet(target, out) == 9 - 1


@pytest.mark.parametrize(
    ("table", "key", "value", "rule"),
    [
        ("graha_drishti", "Jupiter", "5,7,13", "BAD_VALUE"),
        ("graha_drishti", "Pluto", "7", "UNKNOWN_KEY"),
        ("graha_drishti", "Sun", "seven", "BAD_VALUE"),
        ("house_categories", "house_8", "maraka", "BAD_VALUE"),  # D75: never emitted
        ("natural_nature", "Sun", "wicked", "BAD_VALUE"),
        ("signal_priority", "x", "101", "BAD_VALUE"),
        ("signal_priority", "Not An Id", "50", "INVALID_KEY"),
        ("signal_priority", "x.y", "0", "BAD_VALUE"),
        ("suppression", "a", "B C", "BAD_VALUE"),
        ("nope", "a", "1", "UNKNOWN_TABLE"),
    ],
)
def test_rules_bad_rows(tmp_path: Path, table: str, key: str, value: str, rule: str) -> None:
    target = tmp_path / "r.yaml"
    rep = rules.import_sheet(target, rsheet(tmp_path / "s.csv", [(table, key, value, "approve", "")]), write=True)
    assert rule in {e.rule for e in rep.errors} and not target.exists()


def test_rules_suppression_must_point_at_ranked_signals(tmp_path: Path) -> None:
    sh = rsheet(
        tmp_path / "s.csv",
        [("signal_priority", "a", "50", "approve", ""), ("suppression", "a", "ghost", "approve", "")],
    )
    assert "UNRANKED_SIGNAL" in {e.rule for e in rules.import_sheet(tmp_path / "r.yaml", sh).errors}


def test_rules_decision_rules(tmp_path: Path) -> None:
    t = tmp_path / "r.yaml"
    assert "EDIT_WITH_APPROVE" in {
        e.rule
        for e in rules.import_sheet(
            t, rsheet(tmp_path / "a.csv", [("natural_nature", "Sun", "malefic", "approve", "benefic")])
        ).errors
    }
    assert "EDIT_EMPTY" in {
        e.rule
        for e in rules.import_sheet(
            t, rsheet(tmp_path / "b.csv", [("natural_nature", "Sun", "malefic", "edit", "")])
        ).errors
    }
    dup = rsheet(tmp_path / "c.csv", [("natural_nature", "Sun", "malefic", "approve", "")] * 2)
    assert "DUPLICATE_ROW" in {e.rule for e in rules.import_sheet(t, dup).errors}


def test_complete_table_marks_ruleset_partial_false(tmp_path: Path) -> None:
    rows = [
        ("natural_nature", p, "benefic", "approve", "")
        for p in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
    ]
    t = tmp_path / "r.yaml"
    assert rules.import_sheet(t, rsheet(tmp_path / "s.csv", rows), write=True).ok
    assert yamlio.load(t.read_text())["status"] == "COMPLETE"


# ---------- command line ----------


def test_cli_library_end_to_end(root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "sheet.csv"
    assert main(["library", "export-sheet", "--out", str(out), "--root", str(root), "--kind", "planet_in_house"]) == 0
    rows = sheet.read_rows(out, ("key", "decision"))
    assert len(rows) == 3
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "field", "draft", "decision", "edited", "note"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "decision": "approve"})
    report = tmp_path / "report.md"
    assert main(["library", "import", str(out), "--root", str(root), "--write", "--report", str(report)]) == 0
    assert "Approved" in report.read_text() and "written" in capsys.readouterr().out
    assert main(["library", "verify", "--root", str(root)]) == 0
    bad = make_sheet(tmp_path / "bad.csv", [row("planet_in_house/Jupiter/house_1", "stale", "approve")])
    assert main(["library", "import", str(bad), "--root", str(root)]) == 1


def test_cli_rules(tmp_path: Path) -> None:
    sh = rsheet(tmp_path / "s.csv", [("natural_nature", "Sun", "malefic", "approve", "")])
    f = tmp_path / "r.yaml"
    assert main(["rules", "import", str(sh), "--file", str(f), "--reviewed-on", "2026-11-28", "--write"]) == 0
    assert main(["rules", "verify", "--file", str(f)]) == 0
    assert main(["rules", "export-sheet", "--file", str(f), "--out", str(tmp_path / "o.csv")]) == 0


def test_windows_line_endings_do_not_look_like_hand_edits(root: Path, tmp_path: Path) -> None:
    """Owner's laptop: git on Windows checks files out with CRLF; verify must still pass."""
    library.import_sheet(
        root, make_sheet(tmp_path / "s.csv", [row("planet_in_house/Jupiter/house_1", OK_TEXT, "approve")]), write=True
    )
    for p in root.iterdir():
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    rep = library.verify(root)
    assert rep.ok, rep.errors
