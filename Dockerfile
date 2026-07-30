# FastAPI web service for InsurIntellect Agent
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     HOST=0.0.0.0     PORT=8766

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

EXPOSE 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3     CMD python -c "import os, urllib.request; port=os.getenv('PORT','8766'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health/', timeout=5).read()"

CMD ["sh", "-c", "uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8766}"]
