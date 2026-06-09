# Build/test environment only -- GUI requires display server
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libegl1-mesa \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Smoke test: verify imports (GUI will not render in Docker)
CMD ["python", "-c", "from PyQt5.QtWidgets import QApplication; print('PyQt5 import OK')"]
