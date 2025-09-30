# app/ocr.py
from pathlib import Path
from typing import Optional, Iterable, List, Tuple
import re

import pytesseract
from PIL import Image, ImageOps, ImageFilter

# ---------- الگوها ----------
# الگوهای «بدون فاصله»
RX_SPACELESS = [
    re.compile(r"\b(JTE[A-Z0-9]{6,})\b", re.I),             # J&T
    re.compile(r"\b(AJA[A-Z0-9]{6,})\b", re.I),             # AJEX
    re.compile(r"\b(BG-\d+[A-Z0-9]{6,})\b", re.I),          # نمونه کد BG-...
    re.compile(r"\b\d{10,16}\b"),                           # اینویس‌های عددی 10-16 رقمی
]
# الگوهای با فاصله (J T E 3 0 0 ...)
RX_SPACED = [
    re.compile(r"J\s*T\s*E\s*([A-Z0-9]\s*){6,}", re.I),
    re.compile(r"A\s*J\s*A\s*([A-Z0-9]\s*){6,}", re.I),
    re.compile(r"B\s*G\s*-\s*\d+(\s*[A-Z0-9]\s*){6,}", re.I),
]

# جایگزینی اشتباهات رایج OCR
COMMON_FIXES = (
    ("O", "0"),
    ("I", "1"),
    ("L", "1"),
    ("S", "5"),
    ("B", "8"),
    ("Z", "2"),
    ("Q", "0"),
)

# ---------- کمک‌ها ----------
def _fix_ocr_noise(s: str) -> str:
    s = s.strip()
    # حذف فاصله و علامت‌ها
    s = re.sub(r"[^\w\-]+", "", s, flags=re.UNICODE)
    s = s.upper()
    for a, b in COMMON_FIXES:
        s = s.replace(a, b)
    return s

def _preprocess_variants(img: Image.Image) -> Iterable[Image.Image]:
    """چند نسخه‌ی پیش‌پردازشی برای بهتر شدن OCR تولید می‌کند."""
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)

    # بزرگ‌نمایی برای فونت ریز
    g_big = g.resize((g.width * 2, g.height * 2)) if min(g.size) < 1200 else g.copy()

    variants = [
        g_big,
        g_big.filter(ImageFilter.SHARPEN),
        g_big.point(lambda x: 255 if x > 180 else 0, mode="1"),  # باینری ملایم
        g_big.point(lambda x: 255 if x > 160 else 0, mode="1"),  # باینری سخت‌تر
    ]
    return variants

def _extract_candidates(text: str) -> List[str]:
    """از متن خام، کاندیدها را با regex بیرون می‌کشد (با و بدون فاصله)."""
    cands: List[str] = []

    # حالت spaceless
    t_no = _fix_ocr_noise(re.sub(r"\s+", "", text))
    for rx in RX_SPACELESS:
        for m in rx.finditer(t_no):
            cands.append(_fix_ocr_noise(m.group(0)))

    # حالت spaced
    for rx in RX_SPACED:
        for m in rx.finditer(text):
            cand = _fix_ocr_noise(m.group(0))
            # بعد از حذف فاصله دوباره روی spaceless تست کن
            for rx2 in RX_SPACELESS:
                m2 = rx2.search(cand)
                if m2:
                    cands.append(_fix_ocr_noise(m2.group(0)))

    # یکتا
    uniq = []
    seen = set()
    for c in cands:
        if c not in seen:
            uniq.append(c)
            seen.add(c)
    return uniq

def _score_code(code: str) -> Tuple[int, int]:
    """
    امتیازدهی برای انتخاب بهترین کد:
      - پیشوندهای شناخته‌شده امتیاز بیشتر
      - طول بلندتر کمی بهتر
    """
    c = code.upper()
    if c.startswith("JTE"):
        return (100, len(c))
    if c.startswith("AJA"):
        return (95, len(c))
    if c.startswith("BG-"):
        return (90, len(c))
    if c.isdigit() and 10 <= len(c) <= 16:
        return (85, len(c))
    # سایر موارد
    return (50, len(c))

def _choose_best(cands: List[str]) -> Optional[str]:
    if not cands:
        return None
    # بر اساس امتیاز مرتب کن
    cands_sorted = sorted(cands, key=_score_code, reverse=True)
    return cands_sorted[0]

# ---------- API اصلی ----------
def detect_code_from_image(image_path: str) -> Optional[str]:
    """
    OCR محلی با تسرکت:
      - چند پیش‌پردازش
      - چند کانفیگ تسرکت
      - استخراج و امتیازدهی کاندیدها
    """
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print("OCR open error:", e)
        return None

    configs = [
        "--oem 3 --psm 6",  # بلوک متن
        "--oem 3 --psm 7",  # یک خط
    ]

    texts: List[str] = []
    for v in _preprocess_variants(img):
        for cfg in configs:
            try:
                t = pytesseract.image_to_string(v, lang="eng", config=cfg)
                if t:
                    texts.append(t)
            except Exception as e:
                print("pytesseract error:", e)

    full_text = "\n".join(texts)
    cands = _extract_candidates(full_text)
    best = _choose_best(cands)
    return best
