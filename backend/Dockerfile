# The API. Built and run by docker-compose.prod.yml.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Kolkata

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as a normal user, not root. Uploaded documents live in /data/storage,
# which is a Docker volume so they survive a rebuild.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/storage \
    && chown -R app:app /data /app
USER app

EXPOSE 8000

# Bring the database tables up to date, then start the API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips='*'"]
