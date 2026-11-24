# SPDX-License-Identifier: AGPL-3.0-only
"""Storage layer (F2, D70): the meaning-keyed AI cache and the accounts database.

Only `insight`, `account` and `gateway` may import this package (import-linter). Nothing here
ever stores a person's birth data in the cache: cache keys and values are about placements.
"""
