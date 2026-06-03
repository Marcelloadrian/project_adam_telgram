# Pake base image Python yang ringan
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements lalu install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua file code ke container
COPY . .

# Jalankan bot
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
