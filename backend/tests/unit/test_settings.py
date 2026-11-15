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
    problems = Settings().problems()
    assert any("chart_key_pepper" in p for p in problems) and not any("database_url" in p for p in problems)


def test_dotenv_file_is_read(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("PRANIX_FEATURE_CHAT=true\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRANIX_FEATURE_CHAT", raising=False)
    # The app reads .env; tests switch that off globally (conftest), so opt back in here.
    assert Settings(_env_file=("../.env", ".env")).feature_chat is True  # type: ignore[call-arg]


def test_tests_ignore_a_local_env_file(tmp_path, monkeypatch) -> None:
    # A developer's .env with real keys must not leak into tests (or into real AI calls).
    (tmp_path / ".env").write_text("PRANIX_GROQ_API_KEY=real-looking-key\n")
    monkeypatch.chdir(tmp_path)
    assert Settings().secret_fingerprints()["groq_api_key"] == "missing"


def test_blank_secrets_count_as_missing(monkeypatch) -> None:
    # "PRANIX_X=" with nothing after it must not become an empty key or an empty pepper.
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "LOG_PEPPER", "CHART_KEY_PEPPER"):
        monkeypatch.setenv(f"PRANIX_{name}", "  ")
    s = Settings()
    assert s.groq_api_key is None and s.gemini_api_key is None
    assert s.log_pepper is None and s.chart_key_pepper is None


def test_prod_rejects_short_peppers(monkeypatch) -> None:
    monkeypatch.setenv("PRANIX_ENV", "prod")
    monkeypatch.setenv("PRANIX_LOG_PEPPER", "short")
    monkeypatch.setenv("PRANIX_CHART_KEY_PEPPER", "x" * 64)
    assert Settings().problems() == ["log_pepper must be at least 32 characters in prod"]


def test_data_paths_work_from_any_start_folder(tmp_path, monkeypatch) -> None:
    from pranix.config import settings as st

    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "data").mkdir()
    (repo / "data" / "geonames.sqlite").write_bytes(b"x")
    monkeypatch.setattr(st, "REPO_DIR", repo)
    monkeypatch.setattr(st, "BACKEND_DIR", repo / "backend")
    want = str((repo / "data" / "geonames.sqlite").resolve())
    for cwd in (repo, repo / "backend", tmp_path):  # repo root, backend/, somewhere else
        monkeypatch.chdir(cwd)
        assert st._resolve("../data/geonames.sqlite", "/app/data/geonames.sqlite") == want
        assert st._resolve("data/geonames.sqlite", "/app/data/geonames.sqlite") == want
    # the Docker default falls back to the repo's data/ folder outside Docker
    assert st._resolve("/app/data/geonames.sqlite", "/app/data/geonames.sqlite") == str(
        repo / "data" / "geonames.sqlite"
    )
    # an explicit absolute path is never second-guessed, even if missing
    assert st._resolve("/elsewhere/g.sqlite", "/app/data/geonames.sqlite") == "/elsewhere/g.sqlite"
    assert st._resolve("missing.sqlite", "/app/data/geonames.sqlite") == "missing.sqlite"
