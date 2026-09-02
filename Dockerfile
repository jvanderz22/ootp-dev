# ---- stage 1: build the Angular SPA ----
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build -- --configuration production

# ---- stage 2: python runtime ----
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    PORT=8080

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# backend source (training_data/ ships in the image; datasets/ + processed_classes/
# live on the mounted volume at $DATA_DIR)
COPY *.py ./
COPY attribute_models/ ./attribute_models/
COPY modifiers/ ./modifiers/
COPY models/ ./models/
COPY printers/ ./printers/
COPY rankers/ ./rankers/
COPY scoring/ ./scoring/
COPY utils/ ./utils/
COPY training_data/ ./training_data/
COPY web/ ./web/

COPY --from=frontend /app/frontend/dist/draft-web/browser ./frontend/dist/draft-web/browser

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8080

CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
