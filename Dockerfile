FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

# Install system deps including ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application
COPY . /app

RUN mkdir -p /app/downloads

EXPOSE 5001

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5001", "--timeout", "600", "--workers", "4", "--max-requests", "100", "--max-requests-jitter", "10"]
