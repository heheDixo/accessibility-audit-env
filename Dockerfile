FROM python:3.11-slim

WORKDIR /app

# System deps for Chromium / Playwright
RUN apt-get update && apt-get install -y \
      curl \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (layer cache)
COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install Chromium with all OS deps
RUN playwright install chromium --with-deps

# Copy the environment package into /app/accessibility_audit_env
COPY . /app/accessibility_audit_env/

ENV PYTHONPATH=/app
ENV PLAYWRIGHT_CHROMIUM_ARGS="--no-sandbox --disable-dev-shm-usage --disable-gpu"

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:7860/health || exit 1

CMD ["python", "-m", "accessibility_audit_env.server.app"]
