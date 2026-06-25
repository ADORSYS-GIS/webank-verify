# Stage 1: Build React dashboard (requires Node 20)
FROM node:20-slim AS dashboard-builder
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install
COPY dashboard/ .
RUN npm run build

# Stage 2: Python ML dependencies + model download
FROM python:3.12-slim AS ml-base
WORKDIR /app

# System deps for OpenCV and easyocr
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download easyocr French model (~300 MB)
RUN python -c "import easyocr; easyocr.Reader(['fr'], gpu=False)" 2>/dev/null || true

# Pre-download deepface ArcFace model (~100 MB)
RUN python -c "from deepface import DeepFace; DeepFace.build_model('ArcFace')" 2>/dev/null || true

# Stage 3: Runtime
FROM ml-base AS runtime
WORKDIR /app

# Copy application
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

# Copy built dashboard
COPY --from=dashboard-builder /dashboard/dist ./dashboard/dist

# Download MaxMind GeoLite2 DB (at build time if key provided, else at runtime)
COPY scripts/download-geoip.sh ./scripts/
RUN chmod +x ./scripts/download-geoip.sh && \
    (./scripts/download-geoip.sh 2>/dev/null || echo "GeoIP DB not downloaded — set MAXMIND_LICENSE_KEY at runtime")

EXPOSE 8070

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8070", "--workers", "2"]
