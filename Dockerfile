# --- Stage 1: build the SPA ---
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime serving API + built SPA ---
FROM python:3.12-slim AS runtime
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY backend/ ./
RUN uv pip install --system -e .
COPY --from=frontend /fe/dist ./static
RUN mkdir -p /data
ENV SPROUT_STATIC_DIR=/app/static
ENV SPROUT_DB_PATH=/data/sprout.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
