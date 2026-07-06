# Single-container deployment: FastAPI serves BOTH the API and the web UI
# (at /app/), so one image = the whole app for desktop and mobile browsers.
FROM python:3.12-slim

# RDKit's wheels occasionally dlopen these X libs on import.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + prebuilt frontend (builder.js is already compiled; no Node needed).
COPY src ./src
COPY frontend ./frontend

ENV PYTHONPATH=/app/src
ENV PORT=8000
# Single worker keeps the in-memory reference store consistent. To scale out,
# move GraphStore to a shared DB/redis and raise --workers.
CMD ["sh", "-c", "uvicorn chemgrader.api:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
