FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg (libpq) + gcc (curl_cffi build) + Playwright Chromium libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl wget ca-certificates \
    # Chromium runtime deps needed by Playwright
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf2.0-0 libgtk-3-0 libx11-xcb1 libxcb-dri3-0 \
    libdbus-1-3 fonts-liberation xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" --break-system-packages 2>/dev/null || pip install --no-cache-dir -e ".[dev]"

# Install Playwright's Chromium browser binary into the image
RUN playwright install chromium

# Copy source
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
