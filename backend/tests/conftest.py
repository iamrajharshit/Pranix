# SPDX-License-Identifier: AGPL-3.0-only
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pranix.config.settings import get_settings
from pranix.ephemeris import swe

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "geonames"


@pytest.fixture(scope="session", autouse=True)
def _ephemeris() -> None:
    # CI downloads the .se1 files into PRANIX_EPHE_PATH; without them the engine runs in Moshier mode.
    swe.init(os.environ.get("PRANIX_EPHE_PATH"))


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
