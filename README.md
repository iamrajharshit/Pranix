# Pranix

*Read the sky you were born under.*

Pranix computes a Vedic birth chart (D1 and D9, birth star, Dasha timeline) with a deterministic engine and shows it as a calm, cosmic-themed dashboard of twelve insight cards. An AI only re-words facts the engine supplies; it never does the maths. A guide called VEDA (chat) arrives in Phase 2.

**Status:** phase P0: the chart engine (D1, D9, nakshatras, dignity, Atmakaraka, Vimshottari Dasha, elements, doshas, chakras, unknown-time rule) with golden and property tests.

## Where things are
The design specs (requirements, API contract, decisions) are kept privately by the maintainer and are not part of this repository. The code, tests and the public API documentation generated from it live here.

## Run it locally
Needs Python 3.12 and git (Docker optional).
```
tools/fetch_ephe.sh                  # Swiss Ephemeris data, checksums verified
cd backend
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
../tools/fetch_geonames.sh           # offline place index, about a minute
../tools/fetch_fonts.sh              # fonts for card images (optional)
export PRANIX_EPHE_PATH=../data/ephe             # or put both paths in the repo-root .env
export PRANIX_GEO_DB_PATH=../data/geonames.sqlite
pytest                               # unit, property and golden tests
pranix-ctl selftest                  # golden chart check
uvicorn pranix.gateway.app:app --reload          # http://127.0.0.1:8000/v1/places?q=pune
```
Same checks as CI: `ruff check . && ruff format --check . && mypy && lint-imports && pytest`.
Card images need the Cairo library: present on Linux and macOS (`brew install cairo`); on Windows
the image endpoint answers 503 unless Cairo is installed (for example via the GTK runtime). Everything else works.
Docker: `docker build -f infra/Dockerfile -t pranix . && docker run -p 8000:8000 pranix`.

## Stack
FastAPI + pyswisseph (Python 3.12) · React + TypeScript · Postgres (Neon free) · Gemini and Groq free tiers · Render free hosting. Everything uses free services.

## Licence
AGPL-3.0-only. See `LICENSE`. Swiss Ephemeris (pyswisseph) is used under the AGPL.
