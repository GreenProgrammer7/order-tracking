FROM python:3.11-slim

# تسرکت و ابزارهای لازم
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fas \
    wget \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# پکیج‌ها
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir gunicorn

# کد برنامه
COPY . /app

# Healthcheck ساده روی همون پورتی که Railway تنظیم می‌کند
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s CMD wget -qO- http://127.0.0.1:${PORT}/ || exit 1

# نکته مهم: استفاده از PORT محیطی Railway
CMD ["sh","-c","gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT} app.main:app"]
