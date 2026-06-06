FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libreoffice \
    nodejs \
    npm \
    poppler-utils \
    default-jre \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY System/ckv3/ck_web/_web/package*.json ./System/ckv3/ck_web/_web/
RUN cd System/ckv3/ck_web/_web && npm ci && npx playwright install --with-deps chromium

COPY . .

RUN useradd --create-home --shell /bin/bash ckuser \
    && chown -R ckuser:ckuser /app /ms-playwright
USER ckuser

CMD ["./run.sh"]
