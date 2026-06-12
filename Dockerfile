FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY backend ./backend
COPY frontend ./frontend

# Non-root-Benutzer; /data hält die SQLite-Datenbank (Volume)
RUN useradd --create-home kmuos && mkdir -p /data && chown -R kmuos:kmuos /data /app
USER kmuos

ENV KMUOS_DATABASE_URL=sqlite:////data/kmuos.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)" || exit 1

# Bewusst genau 1 Worker: Event-Bus und Scheduler laufen in-process.
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
