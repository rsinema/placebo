FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

COPY src/ src/
RUN uv sync --no-dev

CMD ["uv", "run", "uvicorn", "placebo_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
