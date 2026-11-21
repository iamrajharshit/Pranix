# SPDX-License-Identifier: AGPL-3.0-only
"""Contract fuzzing (F1, QA-05): Schemathesis generates requests from the app's own OpenAPI
document and checks that no input makes the API fail with a 5xx.

Runs in-process (ASGI) with the fake AI provider and roomy rate limits. Each new endpoint gets
response models, so the schema checks grow stricter as the contract fills in (plan 15.1).
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error

from pranix.config.settings import Settings
from pranix.gateway.app import create_app

ROOT = Path(__file__).resolve().parents[3]
_GEO = Path(tempfile.mkdtemp()) / "geonames.sqlite"
subprocess.run(
    [
        sys.executable,
        str(ROOT / "tools" / "build_geonames.py"),
        str(ROOT / "backend" / "tests" / "fixtures" / "geonames"),
        str(_GEO),
        "--cities",
        "cities_fixture.txt",
    ],
    check=True,
    capture_output=True,
)
APP = create_app(
    Settings(
        env="test",
        geo_db_path=str(_GEO),
        ephe_path=os.environ.get("PRANIX_EPHE_PATH", str(ROOT / "data" / "ephe")),
        llm_fake="ok",
        rate_profiles_per_min=100_000,
        rate_places_per_min=100_000,
        rate_insights_per_min=100_000,
        rate_images_per_min=100_000,
    )
)
schema = schemathesis.openapi.from_asgi("/openapi.json", APP)


@schema.exclude(path_regex=r"\.png$").parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_no_input_causes_a_server_error(case: schemathesis.Case) -> None:
    response = case.call()
    case.validate_response(response, checks=[not_a_server_error])
