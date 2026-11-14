# SPDX-License-Identifier: AGPL-3.0-only
"""Swiss Ephemeris settings are thread-local; results must not depend on the calling thread."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from pranix.ephemeris.master import canonical_json, compute
from pranix.ephemeris.selftest import GOLDEN


def test_same_result_on_worker_threads() -> None:
    main = canonical_json(compute(GOLDEN, date(2026, 11, 14)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: canonical_json(compute(GOLDEN, date(2026, 11, 14))), range(8)))
    assert all(r == main for r in results)
