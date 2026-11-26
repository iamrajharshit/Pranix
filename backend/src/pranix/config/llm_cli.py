# SPDX-License-Identifier: AGPL-3.0-only
"""`pranix-ctl llm check` and `pranix-ctl llm bench` (F5).

check: prints the configured chain (provider, model, host; never a key) and sends one tiny prompt to
       each provider, so you can see at once whether Gemma answers on this machine or on the VM.
bench: runs the real insight prompts for the invented sample chart (8 Dec 1984, 00:20, Pune; with and
       without a birth time) through each provider on its own and prints latency, speed and how many
       answers passed every guardrail. The same command on the PC and on the Oracle VM gives numbers
       you can compare directly (plan 6.3: E2B vs E4B is chosen from these).
Nothing personal is ever sent: the sample chart is invented and payloads are de-identified as usual.
"""

from __future__ import annotations

import argparse
import dataclasses
import statistics
import time
from datetime import date
from typing import Any

from .settings import Settings

AS_OF = date(2026, 11, 14)
PING_SYSTEM = 'Reply with JSON only: {"ok": true}'


def add_parsers(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("llm", help="AI providers: check the chain, benchmark each provider")
    ps = p.add_subparsers(dest="action", required=True)
    ps.add_parser("check", help="list the configured providers and ping each one")
    b = ps.add_parser("bench", help="time the real insight prompts on each provider")
    b.add_argument("--rounds", type=int, default=2, help="repeat each prompt this many times (fresh cache)")
    b.add_argument("--provider", action="append", help="only these providers (e.g. gemma, groq, gemini)")


@dataclasses.dataclass
class _Timed:
    """Wraps a provider to record latency and tokens of every call."""

    inner: Any
    calls: list[tuple[float, int, str]] = dataclasses.field(default_factory=list)  # (seconds, tokens_out, outcome)
    name: str = ""
    model: str = ""
    accepts: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        self.name, self.model = str(self.inner.name), str(self.inner.model)
        self.accepts = frozenset(getattr(self.inner, "accepts", {"facts"}))  # same routing as the real one

    def generate(self, system: str, user: str, timeout: float) -> Any:
        from ..llmgw.providers import ProviderError

        t = time.perf_counter()
        try:
            text, usage = self.inner.generate(system, user, timeout)
        except ProviderError as e:
            self.calls.append((time.perf_counter() - t, 0, e.kind))
            raise
        self.calls.append((time.perf_counter() - t, usage.tokens_out, "ok"))
        return text, usage


def _chain(s: Settings) -> Any:
    from ..llmgw.build import insights_chain

    return insights_chain(s)


def _print_routing(s: Settings) -> bool:
    """Which providers each AI task may use (D82). False when the routing is unsafe (start-up would fail)."""
    from ..llmgw.build import router
    from ..llmgw.tasks import TASKS, RoutingError

    try:
        r = router(s)
    except RoutingError as e:
        print(f"routing: REFUSED: {e}")
        return False
    print("routing (task, data, chain: providers in order; then curated text or prepared answers):")
    for t in TASKS.values():
        names = ", ".join(li.provider.name for li in r.chains[t.chain].links) or "none"
        print(f"  {t.id:<16} {t.data_class:<10} {t.chain}: {names}")
    return True


def check(s: Settings) -> int:
    from ..llmgw.build import describe
    from ..llmgw.providers import ProviderError

    chain = _chain(s)
    print(f"chain: {s.llm_chains}" + (f" (fake: {s.llm_fake})" if s.llm_fake != "off" else ""))
    if not _print_routing(s):
        return 1
    from ..llmgw.build import background_chain, reword_gap_s

    bg = background_chain(s, chain)
    print(
        f"background re-wording: on, one at a time, every {reword_gap_s(s):.0f} s at most (D77)"
        if bg is not None
        else "background re-wording: off (needs PRANIX_LOCAL_LLM_URL and PRANIX_BACKGROUND_REWORD=true)"
    )
    if not chain.links:
        print("no providers configured: every card uses reviewed library text")
        return 1
    bad = 0
    for row, link in zip(describe(chain), chain.links, strict=True):
        t = time.perf_counter()
        try:
            text, _ = link.provider.generate(PING_SYSTEM, "ping", link.timeout or 30.0)
            outcome = "ok" if text.strip() else "empty"
        except ProviderError as e:
            outcome = e.kind
        bad += outcome != "ok"
        ms = (time.perf_counter() - t) * 1000
        print(f"  {row['provider']:<7} {row['model']:<34} {row.get('host', '-'):<28} {outcome:<12} {ms:7.0f} ms")
    return 1 if bad else 0


def bench(s: Settings, rounds: int, only: list[str] | None) -> int:
    from ..ephemeris import swe
    from ..ephemeris.master import compute
    from ..ephemeris.selftest import GOLDEN
    from ..insight import cards
    from ..insight.library import Library
    from ..insight.pipeline import InsightService
    from ..llmgw.chain import Chain, Link
    from ..store.cache import MemoryCacheStore

    swe.init(s.ephe_path)
    charts = [compute(GOLDEN, AS_OF), compute(dataclasses.replace(GOLDEN, birth_time_known=False), AS_OF)]
    lib = Library(allow_drafts=s.allow_drafts)
    links = [li for li in _chain(s).links if not only or li.provider.name in only]
    if not links:
        print("no matching providers configured")
        return 1
    import logging

    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))  # table only
    from ..util.tokenbucket import TokenBucket

    jobs = [(m, label, mod) for m, label in zip(charts, ("time known", "time unknown"), strict=True)
            for mod in sorted(cards.SYNTHESIS)]  # fmt: skip
    for link in links:
        timed = _Timed(link.provider)
        passed = total = 0
        print(f"{link.provider.name}: {len(jobs) * rounds} cards, one at a time (Ctrl+C prints the results so far)")
        try:
            for r in range(rounds):
                for i, (master, label, module) in enumerate(jobs, start=1):
                    # a fresh chain and cache per card: every card is a real call, one failure never
                    # opens the breaker for the rest, and the bench is not slowed by the app's rate limit
                    one = Chain([Link(timed, TokenBucket(100_000), timeout=link.timeout)])
                    before = len(timed.calls)
                    service = InsightService(lib, one, cache=MemoryCacheStore())
                    why: list[str] = []
                    service.on_reject = lambda _m, rule, where, why=why: why.append(
                        f"{rule} ({where})" if where else rule
                    )
                    card = service.card(module, master)
                    if card.get("state") != "ready":
                        continue
                    total += 1
                    passed += card.get("badge") == "ai"
                    call = timed.calls[-1] if len(timed.calls) > before else None
                    how = (
                        "AI text"
                        if card.get("badge") == "ai"
                        else (
                            ("rejected: " + why[-1] if why else "rejected by guardrails")
                            if call and call[2] == "ok"
                            else (call[2] if call else "not called")
                        )
                    )
                    took = f"{call[0]:6.1f} s" if call else "      -"
                    print(
                        f"  [{r * len(jobs) + i:>2}/{len(jobs) * rounds}] {module:<10} {label:<12} {took}  {how}",
                        flush=True,
                    )
        except KeyboardInterrupt:
            print("  stopped by you; results so far:")
        ok = [c for c in timed.calls if c[2] == "ok"]
        secs = sorted(c[0] for c in ok) or [0.0]
        p95 = secs[min(len(secs) - 1, int(len(secs) * 0.95))]
        tps = sum(c[1] for c in ok) / max(sum(c[0] for c in ok), 1e-9)
        errors = sorted({c[2] for c in timed.calls if c[2] != "ok"})
        print(
            f"{'provider':<8} {'model':<32} {'calls':>5} {'passed':>7} {'p50 s':>7} {'p95 s':>7} {'tok/s':>6}  errors"
        )
        print(
            f"{link.provider.name:<8} {link.provider.model:<32} {len(timed.calls):>5} {passed:>3}/{total:<3} "
            f"{statistics.median(secs):>7.1f} {p95:>7.1f} {tps:>6.1f}  {', '.join(errors) or '-'}"
        )
    print("passed = AI answers that cleared every guardrail (no numerals, fear, medical words, unknown facts)")
    return 0


def run(args: argparse.Namespace) -> int:
    s = Settings()
    if args.action == "check":
        return check(s)
    return bench(s, max(1, args.rounds), args.provider)
