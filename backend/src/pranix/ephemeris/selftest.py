# SPDX-License-Identifier: AGPL-3.0-only
"""Boot self-test (ENG-06): a golden chart must reproduce before /readyz reports ready."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .master import BirthInput, compute

# Invented sample (not a real person): 8 Dec 1984, 00:20 IST, Pune.
GOLDEN = BirthInput(datetime(1984, 12, 8, 0, 20), "Asia/Kolkata", 18.5204, 73.8567)
EXPECT = {
    "lagna_sign": "Leo",
    "d9_lagna_sign": "Libra",
    "moon": ("Taurus", "Rohini", 2),
    "atmakaraka": "Saturn",
    "chain": ["Jupiter", "Venus", "Mercury", "Rahu"],
    "deity": "Gauri (Parvati)",
    "colors": ["Saffron", "White", "Black"],
    "syllable": "Va",
}


@dataclass
class SelfTestResult:
    ok: bool
    failures: list[str] = field(default_factory=list)


def run() -> SelfTestResult:
    m = compute(GOLDEN, date(2026, 11, 14))
    moon = next(p for p in m["d1"]["planets"] if p["id"] == "Moon")
    got = {
        "lagna_sign": m["d1"]["lagna"]["sign"],
        "d9_lagna_sign": m["d9"]["lagna"]["sign"],
        "moon": (moon["sign"], moon["nakshatra"], moon["pada"]),
        "atmakaraka": m["purpose"]["atmakaraka"],
        "chain": [p["lord"] for p in m["dasha"]["active_chain"]][:4],
        "deity": m["ishta_devta"]["main"],
        "colors": [c["name"] for c in m["colors"]["swatches"]],
        "syllable": m["naming"]["syllables"][m["naming"]["pada"] - 1]["latin"],
    }
    failures = [k for k, v in EXPECT.items() if got[k] != v]
    return SelfTestResult(ok=not failures, failures=failures)
