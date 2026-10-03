FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS console
WORKDIR /build
COPY apps/console/package*.json ./
RUN npm ci --ignore-scripts
COPY apps/console/ ./
RUN npm run build

FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt
COPY pyproject.toml alembic.ini ./
COPY src/ src/
COPY migrations/ migrations/
COPY policies/ policies/
COPY scripts/public_demo.py scripts/public_demo.py
COPY tests/ tests/
RUN pip install --no-deps -e . && python -m pytest
COPY --from=console /build/dist/ apps/console/dist/
RUN useradd --create-home --uid 10001 demo && chown -R demo:demo /app
USER demo
EXPOSE 10000
ENV PORT=10000
CMD ["python", "scripts/public_demo.py"]
