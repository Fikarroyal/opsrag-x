FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements*.txt /app/backend/
# INSTALL_SBERT=1 adds sentence-transformers (large; real semantic embeddings). Default 0 = hashing embedder.
ARG INSTALL_SBERT=0
RUN pip install -r /app/backend/requirements.txt -r /app/backend/requirements-postgres.txt \
    && if [ "$INSTALL_SBERT" = "1" ]; then pip install -r /app/backend/requirements-ml.txt; fi
COPY backend /app/backend
COPY scripts /app/scripts
COPY data /app/data
ENV DATA_DIR=/app/data
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["sh", "-c", "python ../scripts/bootstrap.py --if-empty && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
