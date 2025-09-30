import os
import json
import tempfile
import re
from google.cloud import vision

# --- تنظیم کلید از Environment Variable ---
cred_content = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not cred_content:
    raise RuntimeError("GOOGLE_CREDENTIALS_JSON env var not set")

# ساخت فایل موقت برای گوگل کلود
with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
    tmp.write(cred_content.encode("utf-8"))
    tmp.flush()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

# --- کلاینت Vision API ---
client = vision.ImageAnnotatorClient()

# --- تابع OCR ---
def detect_code_from_image(path: str) -> str | None:
    """
    OCR روی تصویر انجام می‌دهد و سعی می‌کند کد بسته (JTE, AJA, BG...) را پیدا کند.
    """
    with open(path, "rb") as f:
        content = f.read()
    image = vision.Image(content=content)

    response = client.text_detection(image=image)
    texts = response.text_annotations
    if not texts:
        return None

    full_text = texts[0].description.upper()

    # regex برای پیدا کردن کدها
    patterns = [
        r"(JTE[0-9A-Z]{6,})",      # بارکدهای J&T
        r"(AJA[0-9A-Z]{6,})",      # بارکدهای AJA
        r"(BG[-0-9A-Z]{6,})",      # اینویس‌های BG
        r"\b\d{10,15}\b",          # عددهای طولانی (اینویس نامبر)
    ]

    for p in patterns:
        m = re.search(p, full_text)
        if m:
            return m.group(1)

    return None
