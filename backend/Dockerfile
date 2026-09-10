FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so edits to the source do not invalidate the layer.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "fastapi>=0.115.0" \
      "uvicorn[standard]>=0.32.0" \
      "sqlmodel>=0.0.22" \
      "httpx>=0.27.0" \
      "cryptography>=43.0.0" \
      "pydantic>=2.9.0" \
      "pydantic-settings>=2.5.0"

COPY app ./app

# The SQLite file lives here; mount a volume over it to persist across rebuilds.
RUN mkdir -p /data
ENV DB_PATH=/data/odata_ui.db

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
