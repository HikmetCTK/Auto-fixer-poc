FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install runtime deps plus test tooling used by the Docker sandbox
RUN uv sync --extra dev --no-install-project

# Copy source code
COPY src/ ./src/

# Expose API port
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
