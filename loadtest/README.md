# Load and stress tests

Plan section 15.5. Always with the **fake AI provider** (`PRANIX_LLM_FAKE=ok`): real providers are
never load-tested (it would burn free quotas and break their terms). Births come from a fixed
pool of 200 invented ones.

## Run

```bash
pip install -e "backend[load]"                 # Locust
loadtest/serve_for_load.sh                     # API on :8000, pinned to 2 CPUs like the Oracle VM
locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 --headless -u 25 -r 5 -t 3m \
       --csv loadtest/results/run
```

For the full "Oracle-like" stack (production image, 2 CPUs, 350 MB memory limit):

```bash
docker compose -f loadtest/compose.yaml up --build -d
```

| Run | Users | Ramp | Length | Pass when |
|---|---|---|---|---|
| Load | 25 | 5/s | 10 min | p95 ≤ 50 ms per route, no 5xx, app memory ≤ 350 MB |
| Stress | ramp to 200+ | 10/s | until it breaks | past the knee the app answers 429, never crashes |
| Spike | 25 → 250 for 1 min | instant | 5 min | 429s, no 5xx, back to normal within a minute (real rate limits on) |
| Soak | 25 | 5/s | 1 h | flat memory and open files |

## Baseline: 21 Nov 2026, before the Inspector work (F1)

Today's guest API (places, profile, insights SSE, dasha, delete), fake provider, API pinned to
2 cores. **Caveat:** the machine had only 2 cores, shared by Locust and the API, so these
numbers understate the server; the VM run in track H is the real reference.

| Run | Requests/s | p50 | p95 | p99 | Errors | API memory (RSS) |
|---|---|---|---|---|---|---|
| Load, 25 users, 2 min | 38 | 3 ms | 8 ms | 13 ms | 0 | 141 → 171 MB |
| Stress, ramp to 200 users, 100 s | 205 | 44 ms | 150 ms | 250 ms | 0 | 171 → 223 MB |

Per route at 25 users (p95): places 10 ms, create profile 10 ms, full insights stream (12 cards)
7 ms, dasha 5 ms. No knee was reached at 200 users on this machine.
