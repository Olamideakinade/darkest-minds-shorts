# Multi-platform Linux container for Mhide Story Intelligence
FROM python:3.11-slim

# Prevent Python from writing .pyc and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (FFmpeg, essential fonts for captions, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and entrypoints
COPY . .

# Ensure storage directories exist
RUN mkdir -p data/audio data/asset_cache data/research_cache data/curated_assets output/jobs logs credentials

# Make entrypoint executable
RUN chmod +x run.sh

# Default command runs both the Telegram control bot and autonomous scheduler
CMD ["sh", "-c", "python app/main.py bot & python app/main.py daemon --interval 60"]
