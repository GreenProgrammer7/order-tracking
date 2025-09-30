from pathlib import Path
from typing import Optional, Iterable
import re

import pytesseract
from PIL import Image, ImageOps, ImageFilter

# الگوهای کد (همراه نسخه‌ای که فاصله‌های بین حروف را هم تحمل کند)
PATTERNS_SPACELESS = [
    re.compile(r"(JTE[A-Za-z0-9]{6,})", re.I),   # J&T
    re.compile(r"(AJA[A-Za-z0-9]{6,})", re.I),   # AJEX
    re.compile(r"(\d{10,16})"),                  # اینویس‌های عددی بلند
]
PATTERNS_SPACED = [
    re.compile(r"J\s*T\s*E\s*([A-Za-z0-9]\s*){6,}", re.I),
    re.compile(r"A\s*J\s*A\s*([A-Za-z0-9]\s*){6,}", re.I),
]

# جایگزینی اشتباهات رایج OCR
COMMON_FIXES = (
    ("O", "0"),
    ("I", "1"),
    ("l", "1"),
    ("S", "5"),
    ("B", "8"),
    ("Z", "2"),
    ("Q", "0"),
)

def _fix_ocr_noise(s: str) -> str:
    s = s.strip()
    # خیلی از خروجی‌ها با فاصله و خط جدید میان
    s = re.sub(r"[^\w]+", "", s, flags=re.UNICODE)
    # Uppercase
    s = s.upper()
    # جایگزینی اشتباهات
    for a, b in COMMON_FIXES:
        s = s.replace(a, b)
    return s

def _preprocess_variants(img: Image.Image) -> Iterable[Image.Image]:
    """چند نسخه‌ی متفاوت از تصویر برای بهتر شدن OCR تولید می‌کند."""
    # نسخه پایه: خاکستری + اتوکنتراست
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)

    # upscale برای فونت‌های ریز
    if min(g.size) < 1200:
        g_big = g.resize((g.width * 2, g.height * 2))
    else:
        g_big = g.copy()

    variants = []

    # 1) فقط خاکستری بزرگ‌شده
    variants.append(g_big)

    # 2) شارپ
    variants.append(g_big.filter(ImageFilter.SHARPEN))

    # 3) باینری ملایم
    v = g_big.point(lambda x: 255 if x > 180 else 0, mode="1")
    variants.append(v)

    # 4) باینری سخت‌تر
    v2 = g_big.point(lambda x: 255 if x > 160 else 0, mode="1")
    variants.append(v2)

    return variants

def _extract_code_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    # متن خام
    txt_raw = text

    # متن بدون فاصله/علامت (برای match فضادار)
    txt_nospace = re.sub(r"\s+", "", txt_raw)
    txt_nospace = _fix_ocr_noise(txt_nospace)

    # 1) روی متن spaceless (سریع‌تر/تمیزتر)
    for rx in PATTERNS_SPACELESS:
        m = rx.search(txt_nospace)
        if m:
            return m.group(1).upper()

    # 2) تلاش روی متن با فاصله (مثل J T E 3 0 0 ...)
    for rx in PATTERNS_SPACED:
        m = rx.search(txt_raw)
        if m:
            # فاصله‌ها را حذف و نرمال کنیم
            candidate = _fix_ocr_noise(m.group(0))
            # دوباره روی candidate spaceless جست‌وجو کن
            for rx2 in PATTERNS_SPACELESS:
                m2 = rx2.search(candidate)
                if m2:
                    return m2.group(1).upper()

    return None

def detect_code_from_image(image_path: str) -> Optional[str]:
    """
    OCR محلی با تسرکت: چند پیش‌پردازش + چند کانفیگ.
    خروجی: اولین کد معتبر یا None.
    """
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print("OCR open error:", e)
        return None

    texts = []

    # کانفیگ‌های مفید تسرکت
    configs = [
        "--oem 3 --psm 6",  # بلوک متن
        "--oem 3 --psm 7",  # یک خط
    ]

    for v in _preprocess_variants(img):
        for cfg in configs:
            try:
                t = pytesseract.image_to_string(v, lang="eng", config=cfg)
                if t:
                    texts.append(t)
            except Exception as e:
                print("pytesseract error:", e)

    # همه متن‌ها را یکی کن و استخراج کن
    full_text = "\n".join(texts)
    code = _extract_code_from_text(full_text)
    return code
