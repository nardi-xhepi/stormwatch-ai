FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (if any needed, e.g. for kafka)
# build-essential might be needed for some python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY web/ ./web/
COPY config/ ./config/
COPY DATA_SCHEMAS.md .

# Set python path to include root for imports
ENV PYTHONPATH=/app

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "web.api"]
