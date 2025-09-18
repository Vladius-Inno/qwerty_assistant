FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Create app directory
WORKDIR /app

# System dependencies (for building wheels if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY qwerty_webapp/requirements.txt /app/qwerty_webapp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/qwerty_webapp/requirements.txt

# Copy webapp sources
COPY qwerty_webapp /app/qwerty_webapp

# Switch to app folder so assets_dir="assets" resolves correctly
WORKDIR /app/qwerty_webapp/app

# Configure Flet server to listen externally
ENV FLET_SERVER_PORT=8080 \
    FLET_SERVER_IP=0.0.0.0

EXPOSE 8080

# API_BASE_URL is passed at runtime (remote backend)
CMD ["python", "app.py"]

