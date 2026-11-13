# Multi stage image: builds the dashboard, then runs the Python server.
FROM node:22-alpine AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 DAYFOLD_DATA_DIR=/data DAYFOLD_WEB_DIR=/app/web
WORKDIR /app/backend
COPY backend/ ./
RUN pip install --no-cache-dir .
COPY --from=web /src/frontend/dist /app/web
VOLUME /data
EXPOSE 8422
CMD ["dayfold", "serve"]
