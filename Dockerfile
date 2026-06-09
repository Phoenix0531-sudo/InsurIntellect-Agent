# FastAPI service for InsurIntellect Agent
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Smoke test: verify imports, then start server
CMD ["python", "-c", "from app.core.rag_workflow import InsurIntellectAgent; print('Import OK')"]
