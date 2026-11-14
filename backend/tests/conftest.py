# SPDX-License-Identifier: AGPL-3.0-only
import os

import pytest

from pranix.ephemeris import swe


@pytest.fixture(scope="session", autouse=True)
def _ephemeris() -> None:
    # CI downloads the .se1 files into PRANIX_EPHE_PATH; without them the engine runs in Moshier mode.
    swe.init(os.environ.get("PRANIX_EPHE_PATH"))
