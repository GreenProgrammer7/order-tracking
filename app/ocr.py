from typing import Optional, List, Tuple
import re
import easyocr

# الگوهای متنیِ نزدیک به چیزی که گفتی
CONTEXT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("INVOICE", re.compile(r"Invoice\s*Number[:\s]+(\d{10,15})", re.I)),
]

CARRIER_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bJTE[0-9]{8,}\b", re.I),   # J&T Express
    re.compile(r"\bAJA[0-9]{6,}\b", re.I),   # AJEX
]

FALLBACK_NUMBER = re.compile(r"\b\d{12,13}\b")

# Reader را یک بار بسازیم تا سریع‌تر شود
_reader: easyocr.Reader | None = None
def _get_reader():
    global _reader
    if _reader is None:
        # زبان انگلیسی کفایت می‌کند (labels انگلیسی‌اند)
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _reader

def detect_code_from_image(path: str) -> Optional[str]:
    reader = _get_reader()
    # result: لیستی از (bbox, text, confidence)
    results = reader.readtext(path, detail=1, paragraph=True)
    # فقط متن‌ها را یکجا جمع کنیم
    texts = [t[1] for t in results if len(t) >= 2 and isinstance(t[1], str)]
    all_text = "\n".join(texts)

    # 1) نزدیک به Invoice Number
    for name, pat in CONTEXT_PATTERNS:
        m = pat.search(all_text)
        if m:
            return m.group(1).strip()

    # 2) پیشوندهای حامل
    for pat in CARRIER_PATTERNS:
        m = pat.search(all_text)
        if m:
            return m.group(0).upper().strip()

    # 3) fallback: عدد بلند عمومی
    m = FALLBACK_NUMBER.search(all_text)
    if m:
        return m.group(0)

    return None
