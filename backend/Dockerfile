FROM python:3.11-slim

WORKDIR /app

# Install uv for extremely fast python package management
RUN pip install uv

COPY requirements.txt .

# Use uv to install dependencies
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Install aiosqlite explicitly for async sqlite
RUN uv pip install --system aiosqlite

COPY . /app/suspensionlab/backend

ENV PYTHONPATH=/app
ENV DATABASE_URL="sqlite+aiosqlite:////app/data/suspensionlab.db"

# Create data directory
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "suspensionlab.backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
