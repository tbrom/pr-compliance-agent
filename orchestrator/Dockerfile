# Use the official Python layer
FROM python:3.11-slim

WORKDIR /app

# Upgrade pip and install standard build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
    
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the FastAPI server natively via uvicorn spanning all submodules
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
