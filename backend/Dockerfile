# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so edits to the source do not invalidate the layer.
COPY pyproject.toml ./

# The two BuildKit secrets are mounted by docker-build.yml when the caller passes
# mount-pip-index: true - a credential-free Nexus index URL plus a ~/.netrc holding
# the credentials, so neither ends up in a layer or in `docker history`. The CI
# runners have no route to pypi.org, and a plain `pip install` there fails with a
# bare "exit code: 1" from the RUN step.
#
# Both are optional on purpose: with no secret mounted the file is empty, pip falls
# back to its default index, and a local `docker compose build` works unchanged.
# --trusted-host is needed because the Nexus index is served over plain HTTP.
RUN --mount=type=secret,id=pip_index_url \
    --mount=type=secret,id=netrc,target=/root/.netrc \
    set -eu; \
    if [ -s /run/secrets/pip_index_url ]; then \
      index_url="$(tr -d '\r\n' < /run/secrets/pip_index_url)"; \
      hostpart="${index_url#*://}"; hostpart="${hostpart%%/*}"; \
      index_host="${hostpart##*@}"; index_host="${index_host%%:*}"; \
      echo "installing from the Nexus index (host: $index_host)"; \
      set -- --index-url "$index_url" --trusted-host "$index_host"; \
    else \
      echo "no pip_index_url secret mounted - using the default index"; \
      set --; \
    fi; \
    pip install --no-cache-dir --no-input "$@" \
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
