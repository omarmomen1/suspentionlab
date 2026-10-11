# ── Builder stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libeigen3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, deterministic dependency resolution
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# Copy dependency files
COPY pyproject.toml ./
COPY src/ ./src/

# Create virtual environment and install dependencies (core + prod extras)
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -e ".[prod]"

# Compile native C++ kinematics core for Linux target (fails hard if compiler, Eigen, or pybind11 is missing)
RUN rm -f src/suspensionlab/physics/kinematics_core*.so \
    && cmake -B /tmp/kinematics_build -S src/kinematics_cpp -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    && cmake --build /tmp/kinematics_build --config Release \
    && ls -la src/suspensionlab/physics/kinematics_core*.so

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Create non-root user and group
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/false --no-create-home appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code and migration config with correct ownership from builder
COPY --chown=appuser:appgroup --from=builder /app/src/ /app/src/
COPY --chown=appuser:appgroup --from=builder /app/src/suspensionlab/physics/kinematics_core*.so /app/src/suspensionlab/physics/
COPY --chown=appuser:appgroup alembic/ /app/alembic/
COPY --chown=appuser:appgroup alembic.ini /app/

# Environment configuration
ENV PYTHONPATH="/app/src"
ENV ENVIRONMENT="PROD"
ENV PYTHONUNBUFFERED=1
ENV NUMBA_CACHE_DIR="/tmp"

EXPOSE 8000

# Drop privileges to non-root appuser
USER appuser

# Exec form CMD for clean SIGTERM / SIGINT signal propagation
CMD ["python", "-m", "uvicorn", "suspensionlab.backend.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
