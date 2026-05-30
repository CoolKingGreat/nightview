FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TREND_PARQUET_PATH=/app/data/processed/trends.parquet

COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY backend/app /app/app
COPY data/processed/trends.parquet /app/data/processed/trends.parquet
COPY data/raw/cities_seed.csv /app/data/raw/cities_seed.csv

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
