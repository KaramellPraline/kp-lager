# KP Lager – läuft auf amd64 und arm64.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app

FROM python:3.13-slim
WORKDIR /app
RUN useradd --system --uid 1000 lager && mkdir /data && chown lager /data
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" LAGER_DATA_DIR=/data PYTHONUNBUFFERED=1
USER lager
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
