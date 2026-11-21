# SPDX-License-Identifier: AGPL-3.0-only
"""Load, stress, spike and soak scenarios (F1, plan 15.5).

Always against the fake AI provider (PRANIX_LLM_FAKE=ok): real providers are never load-tested.
Births are invented and drawn from a fixed pool, so runs are repeatable and caches behave like
real traffic (many different charts, some repeats).

  locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 --headless -u 25 -r 5 -t 3m \
         --csv loadtest/results/baseline
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

AGE = {"X-Age-Confirmed": "true"}
RNG = random.Random(1984)
# 200 invented births: random dates, times and fixture-index places (no real people).
PLACES = [{"lat": 18.5204, "lon": 73.8567}, {"lat": 19.076, "lon": 72.8777}, {"lat": 28.6139, "lon": 77.209},
          {"lat": 12.9716, "lon": 77.5946}, {"lat": 40.7128, "lon": -74.006}]
BIRTHS = [
    {
        "place": RNG.choice(PLACES),
        "local_datetime": f"{RNG.randint(1950, 2006)}-{RNG.randint(1, 12):02d}-{RNG.randint(1, 28):02d}T"
        f"{RNG.randint(0, 23):02d}:{RNG.randint(0, 59):02d}:00",
        "birth_time_known": RNG.random() > 0.1,
    }
    for _ in range(200)
]


class Guest(HttpUser):
    """A guest: finds a place, creates a chart, reads the dashboard, sometimes starts over."""

    wait_time = between(1, 4)

    @task(6)
    def dashboard(self) -> None:
        self.client.get("/v1/places", params={"q": random.choice(["pune", "mumbai", "delhi"])}, name="/v1/places")
        birth = random.choice(BIRTHS)
        r = self.client.post("/v1/profiles", json=birth, headers=AGE, name="/v1/profiles")
        if r.status_code != 201:
            return
        pid = r.json()["profile_id"]
        # The whole SSE stream is timed: twelve insight events, then done.
        with self.client.get(
            f"/v1/profiles/{pid}/insights", name="/v1/profiles/[id]/insights", stream=True, catch_response=True
        ) as s:
            events = sum(1 for line in s.iter_lines() if line.startswith(b"event: insight"))
            if s.status_code == 200 and events != 12:
                s.failure(f"expected 12 insight events, got {events}")
        with self.client.get(f"/v1/profiles/{pid}/dasha", name="/v1/profiles/[id]/dasha", catch_response=True) as d:
            if d.status_code == 422 and not birth["birth_time_known"]:
                d.success()  # expected: the dasha needs a birth time (D56)
        if random.random() < 0.3:
            self.client.delete(f"/v1/profiles/{pid}", name="/v1/profiles/[id] DELETE")

    @task(1)
    def health(self) -> None:
        self.client.get("/readyz", name="/readyz")
