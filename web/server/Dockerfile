# Build context: repo root (see web/deploy/docker-compose.yml)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ITOPS_CONFIG_DIR=/app/config
RUN useradd --system --uid 10001 --home /app itops
WORKDIR /app/server

COPY web/server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/server/ /app/server/
COPY web/actions/ /app/actions/
COPY config/apps_common.json config/apps_teams.json config/debloat_list.json config/tweaks.json /app/config/

USER itops
EXPOSE 8000
# One worker: live agent connections are held in memory (see app/hub.py).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-server-header"]
