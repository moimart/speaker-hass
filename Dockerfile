FROM python:3.11-slim-bookworm

# Install ALSA utilities for audio capture/playback
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    libasound2 \
    libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install test dependencies (optional, for test stage)
COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

# Copy application code and tests
COPY app/ ./app/
COPY tests/ ./tests/
COPY pytest.ini .

# Create models directory
RUN mkdir -p /models

EXPOSE 8080 10700

CMD ["python", "-m", "app.main"]
