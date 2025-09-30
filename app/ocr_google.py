# app/ocr_google.py
import os, tempfile, re
from typing import Optional

_client = None  # lazy
_GOOD_ENV = "GOOGLE_CREDENTIALS_JSON"
_B64_ENV  = "GOOGLE_CREDENTIALS_JSON_B64"

def _ensure_client():
    global _client
    if _client is not None:
        return

    cred_content = os.getenv(_GOOD_ENV)
    if not cred_content:
        b64 = os.getenv(_B64_ENV)
        if b64:
            import base64
            cred_content = base64.b64decode(b64).decode("utf-8")

    if not cred_content:
        print("[ocr] credentials env var not set; OCR disabled")
        _client = False
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        tmp.write(cred_content.encode("utf-8"))
        tmp.flush()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

    from google.cloud import vision
    _client = vision.ImageAnnotatorClient()

def detect_code_from_image(path: str) -> Optional[str]:
    _ensure_client()
    if not _client:
        return None

    from google.cloud import vision
    with open(path, "rb") as f:
        img = vision.Image(content=f.read())

    resp = _client.text_detection(image=img)
    ann = resp.text_annotations or []
    if not ann:
        return None

    text = ann[0].description.upper()
    patterns = [
        r"(JTE[0-9A-Z]{6,})",
        r"(AJA[0-9A-Z]{6,})",
        r"(BG[-0-9A-Z]{6,})",
        r"\b\d{10,15}\b",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None
