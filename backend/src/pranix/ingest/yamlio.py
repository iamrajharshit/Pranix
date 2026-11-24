# SPDX-License-Identifier: AGPL-3.0-only
"""Canonical YAML writer for the files the importers own.

One fixed layout (keys in the given order, strings always double-quoted JSON style, leaf entries
on one line) so the same data always gives the same bytes. That makes the manifest hash stable and
pull-request diffs small. Reading uses `yaml.safe_load`, so any YAML reader can open the files.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

import yaml

_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.@-]*$")
_RESERVED = {"y", "n", "yes", "no", "on", "off", "true", "false", "null", "~"}


def _key(k: Any) -> str:
    s = str(k)
    if _PLAIN_KEY.match(s) and s.lower() not in _RESERVED:
        return s
    return json.dumps(s, ensure_ascii=False)


def _scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    raise TypeError(f"unsupported scalar {type(v).__name__}")


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, str))


def _is_flow_list(v: Any) -> bool:
    return isinstance(v, Sequence) and not isinstance(v, str) and all(_is_scalar(x) for x in v)


def _is_leaf(v: Any) -> bool:
    return isinstance(v, Mapping) and "status" in v and all(_is_scalar(x) for x in v.values())


def _flow_map(v: Mapping[str, Any]) -> str:
    return "{" + ", ".join(f"{_key(k)}: {_scalar(x)}" for k, x in v.items()) + "}"


def _lines(node: Mapping[str, Any], depth: int) -> list[str]:
    pad = "  " * depth
    out: list[str] = []
    for k, v in node.items():
        if _is_leaf(v):
            out.append(f"{pad}{_key(k)}: {_flow_map(v)}")
        elif _is_flow_list(v):
            out.append(f"{pad}{_key(k)}: [" + ", ".join(_scalar(x) for x in v) + "]")
        elif isinstance(v, Mapping):
            out.append(f"{pad}{_key(k)}:")
            out.extend(_lines(v, depth + 1))
        else:
            out.append(f"{pad}{_key(k)}: {_scalar(v)}")
    return out


def dump(data: Mapping[str, Any], header: Sequence[str] = ()) -> str:
    """SPDX line, then `header` comment lines, then the data. Always ends with one newline."""
    lines = ["# SPDX-License-Identifier: AGPL-3.0-only", *(f"# {h}" for h in header)]
    lines.extend(_lines(data, 0))
    return "\n".join(lines) + "\n"


def load(text: str) -> dict[str, Any]:
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}
