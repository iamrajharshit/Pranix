# Pranix

*Read the sky you were born under.*

Pranix computes a Vedic birth chart (D1 and D9, birth star, Dasha timeline) with a deterministic engine and shows it as a calm, cosmic-themed dashboard of twelve insight cards. An AI only re-words facts the engine supplies; it never does the maths. A guide called VEDA (chat) arrives in Phase 2.

**Status:** phase P0: the chart engine (D1, D9, nakshatras, dignity, Atmakaraka, Vimshottari Dasha, elements, doshas, chakras, unknown-time rule) with golden and property tests.

## Where things are
The design specs (requirements, API contract, decisions) are kept privately by the maintainer and are not part of this repository. The code, tests and the public API documentation generated from it live here.

## Run it locally
Needs Python 3.12, Node 22 and git (Docker optional). Backend first (terminal 1):
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
Then the app (terminal 2). Vite forwards `/v1`, `/version`, `/healthz` and `/readyz` to the backend on port 8000:
```
cd web
npm ci
npm run dev                          # open http://localhost:5173
```
Frontend checks: `npm run typecheck && npm test && npm run build`. To try the production setup instead,
run `npm run build` and start uvicorn with `PRANIX_WEB_DIST=../web/dist`: the app is then served at
http://127.0.0.1:8000/ from the same origin as the API.

Backend checks, same as CI: `ruff check . && ruff format --check . && mypy && lint-imports && pytest`.
Card images need the Cairo library: present on Linux and macOS (`brew install cairo`); on Windows
the image endpoint answers 503 unless Cairo is installed (for example via the GTK runtime). Everything else works.
Docker: `docker build -f infra/Dockerfile -t pranix . && docker run -p 8000:8000 pranix`.

## Deploy
Always-free hosting on one Oracle Cloud Ampere A1 server (D66): see [deploy/oracle/README.md](deploy/oracle/README.md).
Render's free tier runs the same image as a fallback.

## Stack
FastAPI + pyswisseph (Python 3.12) · React + TypeScript · Postgres (Neon free) · Gemini and Groq free tiers · Oracle Cloud Always Free hosting (Render free as fallback). Everything uses free services.

## Licence
AGPL-3.0-only. See `LICENSE`. Swiss Ephemeris (pyswisseph) is used under the AGPL.
