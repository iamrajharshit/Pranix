# SPDX-License-Identifier: AGPL-3.0-only
"""AI tasks, declared once (D82, docs/design/AI_routing_context_and_cache_for_Inspector_and_VEDA.md §2-§3).

Every call names a task. The task says which chain serves it and what kind of data it carries:

    facts      de-identified chart facts and approved text only (no name, date, time, place, user words)
    user_text  anything the person typed (chat messages, chat history)

Providers declare which kinds they accept (`Provider.accepts`). Gemini's free tier accepts facts only,
because free-tier prompts may be used to improve Google's products (D32). The chain refuses to send a
task to a provider that doesn't accept its data class, and `check_routing` fails start-up when a config
puts such a provider in a chain that serves typed text. The rule is in code, not only in config.

Structured-output schemas stay with the callers (insight, chat): the gateway never imports them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .chain import Chain

DataClass = Literal["facts", "user_text"]
FACTS_ONLY: frozenset[str] = frozenset({"facts"})
ANY_DATA: frozenset[str] = frozenset({"facts", "user_text"})


class RoutingError(Exception):
    """A configuration that could send typed text where it must not go. Raised at start-up."""


@dataclass(frozen=True)
class Task:
    id: str
    chain: str  # "reading" | "chat"; also the budget share it draws from
    data_class: DataClass
    prompt_id: str
    max_output_tokens: int
    timeout_s: float  # FR-LLM-05 (cloud); a local link may set its own longer timeout
    cacheable: bool


TASKS: dict[str, Task] = {
    t.id: t
    for t in (
        Task("card_reading", "reading", "facts", "insight@4", 700, 8.0, True),  # T1, exists (D80)
        Task("inspect_reading", "reading", "facts", "inspect@1", 700, 8.0, True),  # T2, I6
        Task("veda_answer", "reading", "facts", "veda-answer@1", 450, 8.0, True),  # T4, V2
        Task("veda_chat", "chat", "user_text", "veda-chat@1", 450, 8.0, False),  # T5/T6, V1: never cached
    )
}


def check_routing(chains: Mapping[str, Chain], tasks: Mapping[str, Task] = TASKS) -> list[str]:
    """Problems that must stop start-up: a task whose chain is missing, or a chain that serves typed
    text containing a provider that doesn't accept it (D32, D82). An empty chain is fine: the caller
    falls back to curated text or prepared answers."""
    problems: list[str] = []
    for task in tasks.values():
        chain = chains.get(task.chain)
        if chain is None:
            problems.append(f"task {task.id}: no chain named {task.chain!r}")
            continue
        for link in chain.links:
            if task.data_class not in getattr(link.provider, "accepts", FACTS_ONLY):
                problems.append(
                    f"task {task.id} ({task.data_class}) is served by chain {task.chain!r}, "
                    f"which contains {link.provider.name} ({link.provider.model}) that accepts only "
                    f"{', '.join(sorted(getattr(link.provider, 'accepts', FACTS_ONLY)))}"
                )
    return problems
