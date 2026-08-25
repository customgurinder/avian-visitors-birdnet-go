FROM python:3.12-slim AS base

# --- runtime environment ---------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ADAPTER_PORT=9000

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app ./app

# Run as a non-root user (Docker best practice)
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Internal port only (never published to the host — the web service reaches it
# over the private Docker network). Override with ADAPTER_PORT if 9000 clashes
# on a custom network; the web service must be given the same value.
EXPOSE 9000

# Container-level healthcheck hits the dependency-free liveness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('ADAPTER_PORT','9000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz').status==200 else 1)"

# LOG_LEVEL controls both app logs and uvicorn's log level (normalised to
# lowercase, which uvicorn requires). ADAPTER_PORT is the internal listen port.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${ADAPTER_PORT:-9000} --log-level $(printf '%s' \"${LOG_LEVEL:-info}\" | tr '[:upper:]' '[:lower:]') --proxy-headers"]
