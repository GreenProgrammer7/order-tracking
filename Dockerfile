FROM python:3.11-slim

# نصب تسرکت و زبان‌ها
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fas \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# نکته مهم: از PORT که Railway می‌دهد استفاده کن
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
