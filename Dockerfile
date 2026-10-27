FROM python:3.15-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

# 安裝必要的系統依賴
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev

COPY backend ./backend
COPY frontend ./frontend
WORKDIR /app/backend
CMD ["/app/.venv/bin/python", "main.py"]
