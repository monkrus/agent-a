FROM python:3.13-slim

WORKDIR /app

# Install system deps for Pillow (OG image generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev libfreetype6-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create .scans directory (scan results storage)
RUN mkdir -p .scans

EXPOSE 5000

# gunicorn with SSE support (sync workers for EventSource streaming)
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "300", \
     "--keep-alive", "65"]
