# app/main.py
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
import uuid, shutil, re

from fastapi import (
    FastAPI, Depends, Form, HTTPException, Request,
    UploadFile, File
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import select, Session

from .deps import init_db, get_session
from .models import Order, OrderStatus, OrderAlias

# OCR گوگل – پیاده‌سازی‌اش در app/ocr_google.py است
# (در آن فایل اگر کرِدنتیال ست نباشد، چیزی کرش نمی‌کند و None برمی‌گرداند)
from .ocr_google import detect_code_from_image


app = FastAPI(title="Order Tracker")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ---------- Helpers ----------

def resolve_order_by_any_code(code: str, session: Session) -> Optional[Order]:
    """
    اول با خودِ کد سفارش را می‌یابد؛
    اگر نبود، در نگاشت‌ها (alias_code) می‌گردد و Order مربوط به order_code را برمی‌گرداند.
    """
    code = code.strip().upper()
    o = session.exec(select(Order).where(Order.code == code)).first()
    if o:
        return o
    al = session.exec(select(OrderAlias).where(OrderAlias.alias_code == code)).first()
    if al:
        return session.exec(select(Order).where(Order.code == al.order_code)).first()
    return None


# الگوهای حدس کد از نام فایل
CODE_REGEXES = [
    re.compile(r"^([A-Za-z0-9\-]{6,})"),                   # شروع نام فایل یک کد
    re.compile(r"^([A-Za-z0-9\-]+)__"),                    # CODE__anything.jpg
    re.compile(r"\b(JTE[A-Za-z0-9]{6,}|AJA[A-Za-z0-9]{6,})\b", re.I),  # حامل‌ها
    re.compile(r"\b\d{10,16}\b"),                          # اینویس/بارکد عددی بلند
]

def guess_code_from_filename(filename: str) -> Optional[str]:
    name = Path(filename).stem
    for rx in CODE_REGEXES:
        m = rx.search(name)
        if m:
            return m.group(1).upper()
    return None


# ---------- Lifecycle ----------
@app.on_event("startup")
def on_startup():
    init_db()


# ---------- Public pages ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/u", response_class=HTMLResponse)
def track_query(code: str):
    code = code.strip().upper()
    return RedirectResponse(url=f"/u/{code}", status_code=302)

@app.get("/u/{code}", response_class=HTMLResponse)
def track_page(code: str, request: Request, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = resolve_order_by_any_code(code, session)
    return templates.TemplateResponse("track.html", {"request": request, "order": o, "code": code})


# ---------- Public JSON ----------
@app.get("/track")
def track_json(code: str, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = resolve_order_by_any_code(code, session)
    if not o:
        return {"code": code, "status": "NOT_FOUND", "message": "سفارش با این کد یافت نشد."}
    return {"code": o.code, "status": o.status, "image": o.image_path}


# ---------- Orders (admin/operator) ----------
@app.post("/orders")
def create_order(code: str = Form(...), session: Session = Depends(get_session)):
    code = code.strip().upper()
    exists = session.exec(select(Order).where(Order.code == code)).first()
    if exists:
        raise HTTPException(400, "Order already exists")
    o = Order(code=code, status=OrderStatus.NOT_ARRIVED_DXB)
    session.add(o); session.commit(); session.refresh(o)
    return {"ok": True, "code": o.code, "status": o.status}

class SetStatusPayload(BaseModel):
    new_status: str

@app.post("/orders/{code}/set-status")
def set_status(code: str, payload: SetStatusPayload, session: Session = Depends(get_session)):
    code = code.strip().upper()
    valid = {
        OrderStatus.NOT_ARRIVED_DXB,
        OrderStatus.ARRIVED_DXB,
        OrderStatus.IN_TRANSIT_IR,
        OrderStatus.ARRIVED_TEH,
    }
    if payload.new_status not in valid:
        raise HTTPException(400, "Invalid status")
    o = resolve_order_by_any_code(code, session)
    if not o:
        raise HTTPException(404, "Order not found")
    o.status = payload.new_status
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()
    return {"ok": True, "code": o.code, "status": o.status}


# ---------- Manual attach (operator form & API) ----------
@app.get("/manual", response_class=HTMLResponse)
def manual_form(request: Request):
    return templates.TemplateResponse("manual.html", {"request": request})

@app.post("/manual-attach")
def manual_attach(
    code: str = Form(...),
    status: str = Form(OrderStatus.ARRIVED_DXB),
    image: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    code = code.strip().upper()

    # ذخیره فایل
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    # یافتن/ساخت سفارش
    o = resolve_order_by_any_code(code, session)
    if not o:
        o = Order(code=code)
        session.add(o); session.flush()

    # به‌روزرسانی
    o.image_path = rel_path
    o.status = status
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()

    return {"ok": True, "code": o.code, "status": o.status, "image": rel_path}


# ---------- Alias mapping (admin) ----------
class AliasPayload(BaseModel):
    order_code: str     # کد مشتری
    alias_code: str     # کد روی بسته/اینویس/حامل
    carrier: Optional[str] = None

@app.post("/admin/aliases")
def create_alias(payload: AliasPayload, session: Session = Depends(get_session)):
    oc = payload.order_code.strip().upper()
    ac = payload.alias_code.strip().upper()

    # اطمینان از وجود سفارش
    o = session.exec(select(Order).where(Order.code == oc)).first()
    if not o:
        o = Order(code=oc)
        session.add(o); session.flush()

    # اگر از قبل ثبت شده بود
    existed = session.exec(select(OrderAlias).where(OrderAlias.alias_code == ac)).first()
    if existed:
        return {"ok": True, "order_code": existed.order_code, "alias_code": existed.alias_code, "carrier": existed.carrier}

    al = OrderAlias(order_code=oc, alias_code=ac, carrier=payload.carrier)
    session.add(al); session.commit(); session.refresh(al)
    return {"ok": True, "order_code": al.order_code, "alias_code": al.alias_code, "carrier": al.carrier}


# ---------- Bulk status update (admin) ----------
class BulkUpdatePayload(BaseModel):
    start_date: date                 # "2025-09-01"
    end_date: date                   # "2025-09-30"
    new_status: str                  # یکی از مقادیر OrderStatus
    exclude_codes: Optional[List[str]] = None

@app.post("/admin/bulk-update-status")
def bulk_update_status(payload: BulkUpdatePayload, session: Session = Depends(get_session)):
    valid = {
        OrderStatus.NOT_ARRIVED_DXB,
        OrderStatus.ARRIVED_DXB,
        OrderStatus.IN_TRANSIT_IR,
        OrderStatus.ARRIVED_TEH,
    }
    if payload.new_status not in valid:
        raise HTTPException(400, "Invalid status")

    # نرمال‌سازی
    excludes = set([c.strip().upper() for c in (payload.exclude_codes or []) if c and c.strip()])

    # بازه زمانی inclusive
    start_dt = datetime.combine(payload.start_date, datetime.min.time())
    end_dt   = datetime.combine(payload.end_date,   datetime.max.time())

    orders = session.exec(
        select(Order).where(Order.created_at >= start_dt, Order.created_at <= end_dt)
    ).all()

    updated = 0
    affected_codes = []
    for o in orders:
        if o.code in excludes:
            continue
        o.status = payload.new_status
        o.updated_at = datetime.utcnow()
        session.add(o)
        updated += 1
        affected_codes.append(o.code)

    session.commit()
    return {"ok": True, "updated_count": updated, "new_status": payload.new_status, "affected_codes": affected_codes[:100]}


# ---------- Ingest by coworker (with optional OCR) ----------
@app.post("/ingest-image")
def ingest_image(
    image: UploadFile = File(...),
    hinted_code: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    # ذخیره فایل
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    # تعیین کد: hinted -> filename -> OCR
    code = hinted_code.strip().upper() if hinted_code else guess_code_from_filename(image.filename)
    if not code:
        code = detect_code_from_image(str(dest))

    if not code:
        # نگه‌داشتن برای بازبینی دستی
        return {"ok": False, "needs_review": True, "image": rel_path, "message": "کد پیدا نشد یا تعریف نشده است."}

    # پیدا کردن سفارش: مستقیم یا از طریق نگاشت
    o = resolve_order_by_any_code(code, session)
    if not o:
        # اگر کدِ داده‌شده alias است ولی نگاشت نداری، بهتره اول /admin/aliases را ثبت کنی
        return {"ok": False, "needs_review": True, "image": rel_path, "detected_code": code, "message": "نگاشت برای این کد تعریف نشده. ابتدا /admin/aliases را ثبت کنید."}

    # به‌روزرسانی سفارش
    o.image_path = rel_path
    if status in (OrderStatus.NOT_ARRIVED_DXB, OrderStatus.ARRIVED_DXB, OrderStatus.IN_TRANSIT_IR, OrderStatus.ARRIVED_TEH):
        o.status = status
    else:
        o.status = OrderStatus.ARRIVED_DXB  # پیش‌فرض وقتی عکس رسید: رسیده دبی
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()

    return {"ok": True, "code": o.code, "status": o.status, "image": rel_path}


# === صفحهٔ اپراتور: فرم آپلود ===
@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


# === آپلود تکی (با fallback به OCR) ===
@app.post("/upload-one")
def upload_one(
    image: UploadFile = File(...),
    hinted_code: str | None = Form(None),
    status: str | None = Form(None),
    session: Session = Depends(get_session),
):
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    # 1) از hinted یا نام فایل
    code = hinted_code.strip().upper() if hinted_code else guess_code_from_filename(image.filename)
    # 2) اگر نشد، OCR
    if not code:
        code = detect_code_from_image(str(dest))

    if not code:
        return {"ok": False, "needs_review": True, "image": rel_path, "message": "کدی یافت نشد."}

    o = resolve_order_by_any_code(code, session)
    if not o:
        return {"ok": False, "needs_review": True, "image": rel_path, "detected_code": code, "message": "نگاشت/سفارش برای این کد تعریف نشده."}

    o.image_path = rel_path
    if status in ("NOT_ARRIVED_DXB","ARRIVED_DXB","IN_TRANSIT_IR","ARRIVED_TEH"):
        o.status = status
    else:
        o.status = "ARRIVED_DXB"
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()

    return {"ok": True, "code": o.code, "status": o.status, "image": rel_path}


# === آپلود چندتایی (با fallback به OCR) ===
@app.post("/upload-many")
def upload_many(
    images: List[UploadFile] = File(...),
    default_status: str = Form("ARRIVED_DXB"),
    session: Session = Depends(get_session),
):
    results = []
    for img in images:
        try:
            ext = Path(img.filename).suffix.lower() or ".jpg"
            fname = f"{uuid.uuid4().hex}{ext}"
            dest = Path("app/static/uploads") / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                shutil.copyfileobj(img.file, f)
            rel_path = f"/static/uploads/{fname}"

            # 1) نام فایل
            code = guess_code_from_filename(img.filename)
            # 2) OCR اگر لازم شد
            if not code:
                code = detect_code_from_image(str(dest))

            if not code:
                results.append({"file": img.filename, "ok": False, "needs_review": True, "image": rel_path, "reason": "CODE_NOT_FOUND"})
                continue

            o = resolve_order_by_any_code(code, session)
            if not o:
                results.append({"file": img.filename, "ok": False, "needs_review": True, "image": rel_path, "detected_code": code, "reason": "ALIAS_NOT_MAPPED"})
                continue

            o.image_path = rel_path
            o.status = default_status if default_status in ("NOT_ARRIVED_DXB","ARRIVED_DXB","IN_TRANSIT_IR","ARRIVED_TEH") else "ARRIVED_DXB"
            o.updated_at = datetime.utcnow()
            session.add(o)
            results.append({"file": img.filename, "ok": True, "code": o.code, "status": o.status, "image": rel_path})
        except Exception as e:
            results.append({"file": getattr(img, 'filename', '?'), "ok": False, "error": str(e)})
    session.commit()
    return {
        "summary": {
            "total": len(images),
            "succeeded": sum(1 for r in results if r.get("ok")),
            "needs_review": sum(1 for r in results if r.get("needs_review")),
        },
        "results": results
    }
