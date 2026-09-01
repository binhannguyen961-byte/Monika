FROM python:3.10-slim

# Cài đặt ffmpeg và các thư viện phụ thuộc hệ thống
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus-dev \
    libopus0 \
    build-essential \
    libffi-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
