# MelosViz bridge — production-oriented image for GHCR
# Build: docker build -t ghcr.io/kooshapari/melosviz-bridge:local -f Dockerfile .
# Run:   docker run --rm -p 8765:8765 ghcr.io/kooshapari/melosviz-bridge:local

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MELOSVIZ_LOG_JSON=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for audio analysis extras (optional; bridge works without librosa)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./backend/
COPY backend/src ./backend/src

RUN pip install --upgrade pip \
 && pip install "./backend[bridge]"

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')" || exit 1

USER nobody
CMD ["python", "-m", "melosviz.bridge.server", "--host", "0.0.0.0", "--port", "8765"]
