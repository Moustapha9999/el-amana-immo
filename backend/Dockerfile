FROM python:3.13-slim

WORKDIR /app

ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY docker-entrypoint.py /docker-entrypoint.py

# Compte non privilégié. Le code reste à root (lecture seule pour l'application) ; seuls les
# dossiers de données lui appartiennent. Dossiers hôte montés : propriétaire uid 10001
# (docs/runbook-migrations.md § Droits des dossiers).
RUN groupadd --system --gid 10001 bea \
    && useradd --system --uid 10001 --gid bea --home-dir /home/bea --create-home --shell /usr/sbin/nologin bea \
    && mkdir -p /app/storage/uploads /app/storage/ged /backups \
    && chown -R bea:bea /app/storage /backups
USER bea

EXPOSE 8000

ENTRYPOINT ["python", "/docker-entrypoint.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
