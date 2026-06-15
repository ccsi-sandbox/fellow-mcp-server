# Builder stage
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target=/build/deps

# Production stage
FROM python:3.11-slim
WORKDIR /app

# Create non-root user
RUN adduser --disabled-password --no-create-home appuser

# Copy dependencies from builder
COPY --from=builder /build/deps /usr/local/lib/python3.11/site-packages

# Copy application code
COPY app/ ./app/
COPY gunicorn.conf.py .

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.main:create_app()"]
