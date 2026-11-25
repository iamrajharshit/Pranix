# SPDX-License-Identifier: AGPL-3.0-only
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from pranix.insight.library import Library, LibraryGap
from pranix.insight.validators import check_text


def strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, Mapping):
        for k, v in node.items():
            if k != "status":
                yield from strings(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_every_library_string_passes_the_guardrails() -> None:
    lib = Library(allow_drafts=True)
    checked = 0
    for path, text in strings(lib.data):
        check_text(path, text)
        checked += 1
    assert checked > 300


def test_approved_batch_and_production_mode() -> None:
    lib = Library(allow_drafts=False)
    # Batch 1 (14 Nov): 26 colours, weekdays, roles. Batch 2 (20 Nov, D69): the other 89 entries.
    # Deep batches 1-5 (25 Nov, D80): the 27 nakshatra_deep entries. Signs batch 1: six sign_deep.
    assert lib.stats() == {"approved": 115 + 27 + 12 + 9, "draft": 0}
    assert lib.get("allies", "colours", "Saffron")["status"] == "approved"
    assert lib.get("signs", "Leo")["status"] == "approved"
    with pytest.raises(LibraryGap):
        lib._ok({"status": "draft"})  # a future draft is still not served in production
    assert Library(allow_drafts=True)._ok({"status": "draft"}) == {"status": "draft"}
    with pytest.raises(LibraryGap):
        lib.get("signs", "Ophiuchus")
