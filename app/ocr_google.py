# app/ocr_google.py
import os, tempfile, re
from typing import Optional

_client = None
_JSON_ENV = "GOOGLE_CREDENTIALS_JSON"
_B64_ENV  = "GOOGLE_CREDENTIALS_JSON_B64"

# پترن‌های رایج روی لیبل‌ها
_PATTERNS = [
    r"\b(JTE[0-9A-Z]{8,})\b",
    r"\b(AJA[0-9A-Z]{8,})\b",
    r"\bBG[-0-9A-Z]{6,}\b",
    r"\b\d{11,16}\b",  # اینویس/بارکد عددی بلند
]

def _ensure_client():
    global _client
    if _client is not None:
        return
    cred_content = os.getenv(_JSON_ENV)
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

def _clean_text(t: str) -> str:
    t = t.upper()
    t = t.replace(" ", "").replace("\n", " ").replace("\r", " ")
    # بعضی اشتباهات رایج OCR
    t = t.replace("JTEO", "JTE0").replace("AJAO", "AJA0")
    return t

def detect_code_from_image(path: str) -> Optional[str]:
    _ensure_client()
    if not _client:
        return None

    from google.cloud import vision
    with open(path, "rb") as f:
        img = vision.Image(content=f.read())

    # دقت بهتر برای اسناد/لیبل‌ها
    resp = _client.document_text_detection(image=img)
    if not resp or not resp.full_text_annotation or not resp.full_text_annotation.text:
        return None

    text = _clean_text(resp.full_text_annotation.text)

    for p in _PATTERNS:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None
