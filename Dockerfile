# FastAPI web service for InsurIntellect Agent
FROM python:3.11-slim

WORKDIR /app

# System dependencies: tesseract-ocr for pytesseract OCR support
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Portfolio local demo uses host port 8766 via scripts/run_demo.*; container default remains 8000.

# Start FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
