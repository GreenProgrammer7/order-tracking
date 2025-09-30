from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlmodel import select, Session
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates
from fastapi import UploadFile, File, Form
from pathlib import Path
import uuid, shutil
from .ocr import detect_code_from_image

from .deps import init_db, get_session, settings
from .models import Order, OrderStatus

app = FastAPI(title="Order Tracker")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/")
def root():
    return {"ok": True, "msg": "Server is up and running!"}

# ساخت سفارش (تو استفاده می‌کنی)
@app.post("/orders")
def create_order(code: str = Form(...), session: Session = Depends(get_session)):
    code = code.strip().upper()
    exists = session.exec(select(Order).where(Order.code == code)).first()
    if exists:
        raise HTTPException(400, "Order already exists")
    o = Order(code=code)
    session.add(o); session.commit(); session.refresh(o)
    return {"ok": True, "code": o.code, "status": o.status}

# تغییر وضعیت به «ارسال شد» (تو استفاده می‌کنی)
@app.post("/orders/{code}/mark-shipped")
def mark_shipped(code: str, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = session.exec(select(Order).where(Order.code == code)).first()
    if not o:
        raise HTTPException(404, "Order not found")
    o.status = OrderStatus.SHIPPED
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()
    return {"ok": True, "code": code, "status": o.status}

# JSON پیگیری
@app.get("/track")
def track_json(code: str, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = session.exec(select(Order).where(Order.code == code)).first()
    if not o:
        return {"code": code, "status": "NOT_FOUND", "message": "سفارش با این کد یافت نشد."}
    payload = {"code": o.code, "status": o.status, "image": o.image_path}
    return payload

# صفحهٔ پیگیری برای مشتری
@app.get("/u/{code}", response_class=HTMLResponse)
def track_page(code: str, request: Request, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = session.exec(select(Order).where(Order.code == code)).first()
    return templates.TemplateResponse("track.html", {"request": request, "order": o, "code": code})

# بالای فایل کنار importهای دیگر اضافه کن:
from fastapi import UploadFile, File
from pathlib import Path
import uuid, shutil

# ... انتهای فایل:

# نمایش فرم آپلود دستی
@app.get("/manual", response_class=HTMLResponse)
def manual_form(request: Request):
    return templates.TemplateResponse("manual.html", {"request": request})

# دریافت فایل و اتصال به سفارش
@app.post("/manual-attach")
def manual_attach(
    code: str = Form(...),
    status: str = Form("ARRIVED"),
    image: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    code = code.strip().upper()

    # ذخیره فایل در /static/uploads
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    # یافتن/ساخت سفارش
    o = session.exec(select(Order).where(Order.code == code)).first()
    if not o:
        o = Order(code=code)
        session.add(o); session.flush()

    # به‌روزرسانی سفارش
    o.image_path = rel_path
    o.status = status
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()

    return {"ok": True, "code": code, "status": o.status, "image": rel_path}
@app.post("/ingest-image")
def ingest_image(
    image: UploadFile = File(...),
    hinted_code: str | None = Form(None),
    status: str | None = Form(None),
    session: Session = Depends(get_session)
):
    # 1) ذخیره فایل
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    # 2) اگر کد دستی ندادند، با OCR از عکس بخوان
    code = hinted_code.strip().upper() if hinted_code else None
    if not code:
        code = detect_code_from_image(str(dest)) or None

    if not code:
        # نشد → بره برای بررسی دستی
        return {"ok": False, "needs_review": True, "image": rel_path, "message": "کد پیدا نشد."}

    # 3) وصل به سفارش (اگر نبود بساز)
    o = session.exec(select(Order).where(Order.code == code)).first()
    if not o:
        o = Order(code=code)
        session.add(o); session.flush()

    o.image_path = rel_path
    if status in (OrderStatus.PENDING, OrderStatus.ARRIVED, OrderStatus.SHIPPED):
        o.status = status
    else:
        o.status = OrderStatus.ARRIVED
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()

    return {"ok": True, "code": code, "status": o.status, "image": rel_path}

