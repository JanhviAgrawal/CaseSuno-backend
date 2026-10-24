# CASE SUNO Backend — production container (alternative to Render's native Python runtime)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN DEBUG=True SECRET_KEY=build-only python manage.py collectstatic --no-input

# Run as non-root user for security
RUN useradd -m casesuno && chown -R casesuno:casesuno /app
USER casesuno

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --no-input && python manage.py ensure_admin --if-configured && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 3 --timeout 120"]
