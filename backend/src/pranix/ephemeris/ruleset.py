# SPDX-License-Identifier: AGPL-3.0-only
"""Versioned ruleset loading (FR-CAL-09). Tables are immutable after load (ENG-03)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from importlib import resources
from types import MappingProxyType
from typing import Any

import yaml


@dataclass(frozen=True)
class Nakshatra:
    name: str
    lord: str
    deity: str
    symbol: str


@dataclass(frozen=True)
class Ruleset:
    id: str
    version: int
    hash: str
    signs: tuple[str, ...]
    sign_lords: tuple[str, ...]
    nakshatras: tuple[Nakshatra, ...]
    exalted: Mapping[str, int]
    debilitated: Mapping[str, int]
    own: Mapping[str, tuple[int, ...]]
    friendship: Mapping[str, Mapping[str, tuple[str, ...]]]
    dasha_order: tuple[str, ...]
    dasha_years: Mapping[str, int]
    dasha_year_days: Fraction
    raw: Mapping[str, Any]

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


def _freeze(d: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(d))


@cache
def load_ruleset(ref: str = "vedic-core@1") -> Ruleset:
    if "/" in ref or "\\" in ref or not ref.endswith(tuple("0123456789")):
        raise ValueError("invalid ruleset reference")
    data = resources.files("pranix.rulesets").joinpath(f"{ref}.yaml").read_bytes()
    raw = yaml.safe_load(data)
    d = raw["dignity"]
    return Ruleset(
        id=raw["id"],
        version=int(raw["version"]),
        hash=hashlib.sha256(data).hexdigest()[:16],
        signs=tuple(raw["signs"]),
        sign_lords=tuple(raw["sign_lords"]),
        nakshatras=tuple(Nakshatra(**n) for n in raw["nakshatras"]),
        exalted=_freeze(d["exalted"]),
        debilitated=_freeze(d["debilitated"]),
        own=_freeze({k: tuple(v) for k, v in d["own"].items()}),
        friendship=_freeze({p: _freeze({k: tuple(v) for k, v in rel.items()}) for p, rel in raw["friendship"].items()}),
        dasha_order=tuple(raw["vimshottari"]["order"]),
        dasha_years=_freeze(raw["vimshottari"]["years"]),
        dasha_year_days=Fraction(str(raw["conventions"]["dasha_year_days"])),
        raw=_freeze(raw),
    )
