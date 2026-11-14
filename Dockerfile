FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    FLASK_DEBUG=0 \
    PORT=8000

WORKDIR /app

# Dependencies first so this layer is cached until pyproject/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# `run:app` is the Flask app created in run.py; secrets come from the environment (--env-file / platform).
CMD ["sh", "-c", "exec .venv/bin/gunicorn run:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120"]
