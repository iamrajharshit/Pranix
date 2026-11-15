# SPDX-License-Identifier: AGPL-3.0-only
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pranix.config.settings import Settings, get_settings
from pranix.ephemeris import swe

# Tests are sealed off from the developer's machine: a real .env (API keys, peppers) and real
# PRANIX_* secrets must never change a result or reach a real AI provider. Only the data-file
# paths CI sets on purpose are kept.
Settings.model_config["env_file"] = None
_KEEP = {"PRANIX_EPHE_PATH", "PRANIX_FONTS_DIR", "PRANIX_GEO_DB_PATH"}
for _k in [k for k in os.environ if k.upper().startswith("PRANIX_") and k.upper() not in _KEEP]:
    del os.environ[_k]

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "geonames"


@pytest.fixture(scope="session", autouse=True)
def _ephemeris() -> None:
    # CI downloads the .se1 files into PRANIX_EPHE_PATH; without them the engine runs in Moshier mode.
    swe.init(os.environ.get("PRANIX_EPHE_PATH"))


# Card-image fonts: CI fetches them into data/fonts (tools/fetch_fonts.sh); tests skip images without them.
os.environ.setdefault("PRANIX_FONTS_DIR", str(ROOT / "data" / "fonts"))


@pytest.fixture(scope="session", autouse=True)
def geo_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the fixture place index with the real build script (so the script is tested too)."""
    out = tmp_path_factory.mktemp("geo") / "geonames.sqlite"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "build_geonames.py"),
            str(FIXTURE),
            str(out),
            "--cities",
            "cities_fixture.txt",
        ],
        check=True,
        capture_output=True,
    )
    os.environ["PRANIX_GEO_DB_PATH"] = str(out)
    get_settings.cache_clear()
    return out
