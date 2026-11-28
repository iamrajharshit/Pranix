# SPDX-License-Identifier: AGPL-3.0-only
"""D86 item 3 (owner sign-off 28 Nov): what each answer may contain, checked on every change.

1. An allowlist: the exact set of field paths each answer may carry. A new field fails this test
   until it is added to public_fields.json on purpose (regenerate with UPDATE_PUBLIC_FIELDS=1).
2. A denylist, checked recursively: birth data, coordinates and internal working never appear in
   any chart, Inspector, timeline or card answer, under any key, at any depth.
3. Precision: every degree sent is a whole arcminute; no answer holds the birth instant.
"""

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from spa_client import TestClient

from pranix.config.settings import Settings
from pranix.gateway.app import create_app

ROOT = Path(__file__).resolve().parents[3]
EXPECTED = Path(__file__).with_name("public_fields.json")
DENY = {
    "birth_date", "birth_time", "local_datetime", "local_date", "dob", "tob", "lat", "lon", "latitude",
    "longitude", "timezone", "tz", "place", "place_id", "pronouns", "person_name", "speed", "working", "contributions",
    "nakshatra_number", "swisseph_version", "rulesets",
}  # fmt: skip
SAMPLE = {"place": {"lat": 18.5204, "lon": 73.8567}, "local_datetime": "1984-12-08T00:20:00"}
UTC_BIRTH = "1984-12-07T18:50"  # the sample birth in UTC: must never be sent


def paths(o: Any, pre: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(o, dict):
        for k, v in o.items():
            if pre.endswith("bundles") or pre.endswith("facts"):
                k = "*"  # dynamic keys: planet:Sun, house:7, moon.sign ...
            out |= {pre + "." + k if pre else k} | paths(v, (pre + "." + k) if pre else k)
    elif isinstance(o, list):
        for v in o:
            out |= paths(v, pre + "[]")
    return out


def keys(o: Any) -> Iterator[str]:
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from keys(v)


def degrees(o: Any, k: str = "") -> Iterator[float]:
    if isinstance(o, dict):
        for kk, v in o.items():
            yield from degrees(v, kk)
    elif isinstance(o, list):
        for v in o:
            yield from degrees(v, k)
    elif k in ("deg_in_sign", "ayanamsa_value") and isinstance(o, float):
        yield o


@pytest.fixture(scope="module")
def answers() -> dict[str, Any]:
    geo = Path(tempfile.mkdtemp()) / "g.sqlite"
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_geonames.py"), str(ROOT / "backend/tests/fixtures/geonames"),
         str(geo), "--cities", "cities_fixture.txt"], check=True, capture_output=True,
    )  # fmt: skip
    app = create_app(Settings(env="test", llm_fake="ok", feature_inspect=True, geo_db_path=str(geo)))
    out: dict[str, Any] = {}
    with TestClient(app) as c:
        for known in (True, False):
            tag = "known" if known else "unknown"
            r = c.post("/v1/profiles", json={**SAMPLE, "birth_time_known": known}, headers={"X-Age-Confirmed": "true"})
            pid = r.json()["profile_id"]
            out[f"profile_{tag}"] = r.json()
            out[f"open_{tag}"] = c.get(f"/v1/profiles/{pid}").json()
            out[f"dasha_{tag}"] = c.get(f"/v1/profiles/{pid}/dasha").json()
            out[f"inspect_d1_{tag}"] = c.get(f"/v1/profiles/{pid}/inspect/d1").json()
            cards = []
            with c.stream("GET", f"/v1/profiles/{pid}/insights") as s:
                for line in s.iter_lines():
                    if line.startswith("data:"):
                        cards.append(json.loads(line[5:]))
            out[f"cards_{tag}"] = cards
            if known:
                out["inspect_d9_known"] = c.get(f"/v1/profiles/{pid}/inspect/d9").json()
        out["version"] = c.get("/version").json()
    return out


def test_every_answer_has_exactly_the_allowed_fields(answers: dict[str, Any]) -> None:
    got = {name: sorted(paths(a)) for name, a in answers.items()}
    if os.environ.get("UPDATE_PUBLIC_FIELDS") == "1":
        EXPECTED.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    expected = json.loads(EXPECTED.read_text())
    for name in got:
        added = sorted(set(got[name]) - set(expected.get(name, [])))
        removed = sorted(set(expected.get(name, [])) - set(got[name]))
        assert not added and not removed, f"{name}: new {added[:8]} / gone {removed[:8]} (see test docstring)"


@pytest.mark.parametrize("name", ["profile", "open", "dasha", "inspect_d1", "cards"])
@pytest.mark.parametrize("tag", ["known", "unknown"])
def test_no_birth_data_or_internal_working_anywhere(answers: dict[str, Any], name: str, tag: str) -> None:
    a = answers[f"{name}_{tag}"]
    assert not (set(keys(a)) & DENY), set(keys(a)) & DENY
    assert UTC_BIRTH not in json.dumps(a)  # C1: the birth instant never leaves the server


def test_every_degree_is_a_whole_arcminute(answers: dict[str, Any]) -> None:
    found = [d for a in answers.values() for d in degrees(a)]
    assert len(found) > 20
    for d in found:
        assert abs(d * 60 - round(d * 60)) < 1e-6, d


def test_the_method_moved_to_version(answers: dict[str, Any]) -> None:
    assert answers["version"]["method"] == {"ayanamsa": "lahiri", "node_type": "mean", "house_system": "whole_sign"}
    assert answers["profile_known"]["master"]["meta"]["schema_version"]  # A6 tweak 1: still on the chart
    assert answers["inspect_d1_known"]["schema_version"] == "1"  # A7: once, at the top
