# SPDX-License-Identifier: AGPL-3.0-only
"""The Chart Inspector's rules (plan §4): pure, deterministic relations read from the Master JSON.

Imports only the engine's ruleset; never the gateway, AI, insight text, storage or config (import-linter).
Text people read (the summary line, glosses) is added outside this package (`insight.inspect_text`).
"""

from .bundle import InspectionBundle, InspectionSet, build_set

__all__ = ["InspectionBundle", "InspectionSet", "build_set"]
