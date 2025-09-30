from pathlib import Path
import re
from typing import Optional

import pytesseract
from PIL import Image, ImageOps, ImageFilter

# الگوهای کد
PATTERNS = [
    re.compile(r"\b(JTE[A-Za-z0-9]{6,})\b", re.I),  # J&T
    re.compile(r"\b(AJA[A-Za-z0-9]{6,})\b", re.I),  # AJEX
    re.compile(r"\b\d{10,15}\b"),                   # اینویس‌های عددی بلند
]

def _preprocess(img: Image.Image) -> Image.Image:
    """
    پیش‌پردازش ساده: تبدیل به خاکستری، افزایش کنتراست، شارپ، باینری.
    """
    g = ImageOps.grayscale(img)
    # upscale برای بهبود OCR روی فونت ریز
    if min(g.size) < 1000:
        scale = 2
        g = g.resize((g.width * scale, g.height * scale))
    # افزایش کنتراست/شارپ
    g = ImageOps.autocontrast(g)
    g = g.filter(ImageFilter.SHARPEN)
    # باینری ساده
    g = g.point(lambda x: 255 if x > 180 else 0, mode='1')
    return g

def _extract_code_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    for rx in PATTERNS:
        m = rx.search(text)
        if m:
            return m.group(1).upper()
    return None

def detect_code_from_image(image_path: str) -> Optional[str]:
    """
    OCR محلی با تسرکت. خروجی: اولین کد معتبر یا None.
    """
    try:
        img = Image.open(image_path).convert("RGB")
        proc = _preprocess(img)
        # انگلیسی کافیه؛ اگر برچسب‌ها فارسی هم دارند: eng+fas
        text = pytesseract.image_to_string(proc, lang="eng")
        # اگر لازم شد: text += "\n" + pytesseract.image_to_string(proc, lang="fas")
        return _extract_code_from_text(text)
    except Exception as e:
        print("OCR error:", e)
        return None
