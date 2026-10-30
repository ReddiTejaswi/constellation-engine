FROM node:22-slim AS frontend-build
WORKDIR /build/frontend
RUN corepack enable && corepack prepare pnpm@10.8.1 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=10000
WORKDIR /app
COPY requirements-prod.txt ./requirements-prod.txt
RUN pip install --no-cache-dir -r requirements-prod.txt \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data/retrieval_cache \
    && chown -R app:app /app
COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN chown -R app:app /app
USER app:app
EXPOSE 10000
CMD ["sh", "-c", "uvicorn backend.api.app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --timeout-graceful-shutdown 2 --proxy-headers --forwarded-allow-ips='*'"]
