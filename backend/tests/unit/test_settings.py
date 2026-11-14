# SPDX-License-Identifier: AGPL-3.0-only
from pranix.config.settings import Settings


def test_secret_values_are_never_shown(monkeypatch) -> None:
    monkeypatch.setenv("PRANIX_GEMINI_API_KEY", "super-secret-value")
    s = Settings()
    fps = s.secret_fingerprints()
    assert "super-secret-value" not in repr(s) and "super-secret-value" not in str(fps)
    assert len(fps["gemini_api_key"]) == 6 and fps["groq_api_key"] == "missing"


def test_prod_requires_secrets(monkeypatch) -> None:
    monkeypatch.setenv("PRANIX_ENV", "prod")
    assert any("database_url" in p for p in Settings().problems())
