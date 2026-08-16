FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY sdk/ ./sdk/
COPY run.py .

# Install SDK locally in editable mode
RUN pip install --no-cache-dir -e ./sdk

EXPOSE 8000

ENV ECHOTRACE_HOST="0.0.0.0"
ENV ECHOTRACE_PORT="8000"
ENV PYTHONUNBUFFERED="1"

CMD ["python", "run.py"]
