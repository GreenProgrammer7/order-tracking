# app/ocr_google.py
from __future__ import annotations

import os
import io
import re
from typing import Iterable, List, Optional

# Pillow
from PIL import Image, ImageOps, ImageFilter

# OpenCV (headless)
import cv2
import numpy as np


# ========= تنظیمات Regex برای کدها =========
# اولویت: JTE*  ->  AJA*  ->  عدد 12..20 رقمی (اینویس‌نامبر)
RX_JTE = re.compile(r"\bJTE[0-9A-Z]{8,}\b", re.IGNORECASE)
RX_AJA = re.compile(r"\bAJA[0-9A-Z]{6,}\b", re.IGNORECASE)
RX_INVOICE_NUM = re.compile(r"\b\d{12,20}\b")


def _load_image(path: str) -> Image.Image:
    img = Image.open(path)
    # به RGB (و خروج از حالت CMYK/P) برای سازگاری با Vision
    return img.convert("RGB")


def _to_cv(img: Image.Image) -> np.ndarray:
    """PIL -> OpenCV BGR"""
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _to_pil(mat: np.ndarray) -> Image.Image:
    """OpenCV BGR -> PIL"""
    return Image.fromarray(cv2.cvtColor(mat, cv2.COLOR_BGR2RGB))


def _resize_max_side(mat: np.ndarray, max_side: int = 1800) -> np.ndarray:
    h, w = mat.shape[:2]
    scale = max_side / float(max(h, w))
    if scale >= 1.0:
        return mat
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(mat, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


def _preprocess_variants(img: Image.Image) -> List[Image.Image]:
    """
    چند نسخه‌ی پیش‌پردازش تولید می‌کند تا شانس OCR بالا برود.
    """
    variants: List[Image.Image] = []

    # 1) نسخه‌ی پایه (resize بزرگ)
    base_cv = _resize_max_side(_to_cv(img), max_side=1800)

    # 2) حذف نویز + شارپ ملایم
    den = cv2.bilateralFilter(base_cv, d=9, sigmaColor=75, sigmaSpace=75)
    den_pil = _to_pil(den).filter(ImageFilter.UnsharpMask(radius=2, percent=120))
    variants.append(den_pil)

    # 3) grayscale + CLAHE + باینری تطبیقی
    gray = cv2.cvtColor(base_cv, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    adapt = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 11
    )
    adapt_bgr = cv2.cvtColor(adapt, cv2.COLOR_GRAY2BGR)
    variants.append(_to_pil(adapt_bgr))

    # 4) افزایش کنتراست (Pillow) + شارپ
    hi = ImageOps.autocontrast(_to_pil(base_cv), cutoff=2)
    hi = hi.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140))
    variants.append(hi)

    # 5) معکوس (گاهی متن تیره روی روشن بهتر می‌شود)
    inv = ImageOps.invert(ImageOps.grayscale(_to_pil(base_cv))).convert("RGB")
    variants.append(inv)

    # برای هر نسخه، چرخش‌های 0/90/180/270 هم تولید می‌کنیم
    final: List[Image.Image] = []
    for v in variants:
        for angle in (0, 90, 180, 270):
            final.append(v.rotate(angle, expand=True))
    return final


def _vision_client():
    """
    اگر کرِدنتیال گوگل نبود یا کتابخانه نصب نبود، None برمی‌گرداند.
    """
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        return None

    try:
        from google.oauth2.service_account import Credentials
        from google.cloud import vision
    except Exception:
        return None

    try:
        creds = Credentials.from_service_account_info(eval(creds_json))
        client = vision.ImageAnnotatorClient(credentials=creds)
        return client
    except Exception:
        # اگر JSON با eval مشکل داشت، تلاش با from_service_account_file
        try:
            if os.path.isfile(creds_json):
                from google.oauth2.service_account import Credentials
                from google.cloud import vision

                creds = Credentials.from_service_account_file(creds_json)
                client = vision.ImageAnnotatorClient(credentials=creds)
                return client
        except Exception:
            return None
    return None


def _vision_ocr(client, pil_img: Image.Image) -> str:
    """
    OCR با Google Vision (full text). اگر خطا بده خالی برمی‌گردد.
    """
    try:
        from google.cloud import vision  # type: ignore
    except Exception:
        return ""

    try:
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=95)
        content = buf.getvalue()

        image = vision.Image(content=content)
        resp = client.document_text_detection(image=image)  # برای متن‌های بلاکی بهتر از text_detection
        if resp.error.message:
            return ""

        if resp.full_text_annotation and resp.full_text_annotation.text:
            return resp.full_text_annotation.text
        return ""
    except Exception:
        return ""


def _pick_code(text: str) -> Optional[str]:
    """
    متن OCR شده را بررسی می‌کند و با اولویت JTE -> AJA -> عدد 12..20 رقمی
    اولین کدی که به نظر معتبر است را برمی‌گرداند.
    """
    if not text:
        return None
    up = text.upper()

    # 1) JTE…
    m = RX_JTE.search(up)
    if m:
        return m.group(0)

    # 2) AJA…
    m = RX_AJA.search(up)
    if m:
        return m.group(0)

    # 3) اینویس نامبر (اعداد بلند)
    m = RX_INVOICE_NUM.search(up)
    if m:
        return m.group(0)

    return None


def detect_code_from_image(image_path: str) -> Optional[str]:
    """
    ورودی: مسیر فایل عکس
    خروجی: رشته‌ی کد کشف‌شده (مثلاً JTE… یا AJA… یا عدد بلند) یا None
    """
    try:
        original = _load_image(image_path)
    except Exception:
        return None

    variants = _preprocess_variants(original)
    client = _vision_client()
    if client is None:
        # بدون کرِدنتیال/کتابخانه نمی‌توان OCR گرفت
        return None

    # از اولین کد معتبر برگرد
    for v in variants:
        text = _vision_ocr(client, v)
        code = _pick_code(text)
        if code:
            return code

    return None
