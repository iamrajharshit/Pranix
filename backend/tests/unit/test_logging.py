# SPDX-License-Identifier: AGPL-3.0-only
from pranix.obs.logging import REDACTED, scrub


def test_blocked_keys_and_patterns_are_redacted() -> None:
    out = scrub(
        None,
        "info",
        {
            "event": "profile.created for a@b.com born 1984-12-08 at 18.5204, 73.8567",
            "name": "Asha",
            "pronouns": "she_her",
            "lat": 18.5,
            "chart_key": "abc123",
        },
    )
    assert out["name"] == out["pronouns"] == out["lat"] == REDACTED
    assert "a@b.com" not in out["event"] and "1984-12-08" not in out["event"] and "18.5204" not in out["event"]
    assert out["chart_key"] == "abc123"
