# Production backend image.
#
# Dependencies are installed during the BUILD (not at container start), the
# image contains only requirements.txt + app/ — never .env — and the process
# runs as an unprivileged user. Uvicorn is deliberately single-worker: the
# AI-tier metrics and escalation cooldowns live in process memory, so extra
# workers would give each one its own copy.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code only. Configuration arrives through environment variables
# (docker compose), so no .env is ever baked into the image.
COPY app ./app

# Run unprivileged: the API reads its bundled knowledge base and writes nothing
# to disk (all state lives in Postgres).
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Liveness probe against the app's own /health route; no internet access needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).getcode() == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
