# circle-llc FastAPI backend — production image
# Multi-stage build: smaller final image, faster cold-starts.

# ---------- Stage 1: deps ----------
FROM python:3.12-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for psutil / google-genai
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --user -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    # Default SQLite path — Railway mounts /data as a volume
    DATABASE_PATH=/data/circle_llc.db \
    PORT=8000

WORKDIR /app

# Copy installed deps from builder
COPY --from=deps /root/.local /root/.local

# Copy app source (orchestrator package only)
COPY orchestrator/ ./orchestrator/

# Data dir for SQLite — created so volume mount has a target
RUN mkdir -p /data

EXPOSE 8000

# Healthcheck — used by Railway and Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3).status==200 else 1)"

# Run uvicorn with a single worker (M2 traffic is light; scale horizontally later)
# Logs go to stdout (Railway captures them)
CMD ["sh", "-c", "uvicorn orchestrator.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
