FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system appuser \
    && useradd --system --gid appuser appuser

COPY --chown=appuser:appuser app/ ./app/

USER appuser

ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --timeout-graceful-shutdown 25"]
