# SPDX-License-Identifier: AGPL-3.0-only
# Pranix single production image (Tier A). Build from the repo root:
#   docker build -f infra/Dockerfile -t pranix .

FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
RUN pip wheel --no-cache-dir --wheel-dir /wheels ./backend
COPY tools/fetch_ephe.sh tools/fetch_ephe.sh
COPY data/ephe/SHA256SUMS data/ephe/SHA256SUMS
RUN tools/fetch_ephe.sh /ephe
# Offline place index (GeoNames, CC BY 4.0); time zones computed from coordinates.
COPY tools/fetch_geonames.sh tools/build_geonames.py tools/
RUN pip install --no-cache-dir /wheels/*.whl && tools/fetch_geonames.sh /geo/geonames.sqlite
# OFL fonts for server-rendered card images (pinned, checksummed).
COPY tools/fetch_fonts.sh tools/
RUN tools/fetch_fonts.sh /fonts

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRANIX_EPHE_PATH=/app/data/ephe
# Cairo for card images (CairoSVG); nothing else from the OS.
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home /app pranix
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY --from=build --chown=root:root /ephe /app/data/ephe
COPY --from=build --chown=root:root /geo/geonames.sqlite /app/data/geonames.sqlite
COPY --from=build --chown=root:root /fonts /app/data/fonts
WORKDIR /app
USER pranix
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "pranix.gateway.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
