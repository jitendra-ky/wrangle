FROM python:3.12-slim

# Prevents .pyc files; enables unbuffered stdout/stderr for clean Docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# postgresql-client provides pg_isready used in entrypoint.sh
# libpq-dev is needed to compile psycopg2 (psycopg2-binary bundles it, but belt-and-suspenders)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

# CMD is overridden per-service in docker-compose.yml
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "zproject.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
