import os
import json
import tempfile
from google.cloud import vision

# موقع استارتاپ: JSON رو از متغیر محیطی بخونیم و بریزیم تو فایل موقت
cred_content = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not cred_content:
    raise RuntimeError("GOOGLE_CREDENTIALS_JSON env var not set")

# ساخت فایل موقت برای کلید
with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
    tmp.write(cred_content.encode("utf-8"))
    tmp.flush()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

client = vision.ImageAnnotatorClient()

def detect_code_from_image(path: str) -> str | None:
    with open(path, "rb") as f:
        content = f.read()
    image = vision.Image(content=content)

    response = client.text_detection(image=image)
    texts = response.text_annotations
    if not texts:
        return None

    full_text = texts[0].description.upper()
    # کدهایی مثل JTE..., AJA..., BG...
    import re
    m = re.search(r"(JTE[0-9A-Z]+|AJA[0-9A-Z]+|BG[-0-9A-Z]+)", full_text)
    if m:
        return m.group(1)

    return None
