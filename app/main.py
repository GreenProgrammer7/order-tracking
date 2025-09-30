from datetime import datetime
from pathlib import Path
import uuid, shutil

from fastapi import FastAPI, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session

from .deps import init_db, get_session, settings
from .models import Order, OrderStatus
# اگر OCR داری:
# from .ocr import detect_code_from_image

app = FastAPI(title="Order Tracker")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
def on_startup():
    init_db()

# ======= صفحهٔ اصلی + ریدایرکت =======

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/u", response_class=HTMLResponse)
def track_query(code: str):
    code = code.strip().upper()
    return RedirectResponse(url=f"/u/{code}", status_code=302)

# ======= APIهای سفارش =======

@app.post("/orders")
def create_order(code: str = Form(...), session: Session = Depends(get_session)):
    code = code.strip().upper()
    exists = session.exec(select(Order).where(Order.code == code)).first()
    if exists:
        raise HTTPException(400, "Order already exists")
    o = Order(code=code)
    session.add(o); session.commit(); session.refresh(o)
    return {"ok": True, "code": o.code, "status": o.status}

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

@app.get("/track")
def track_json(code: str, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = session.exec(select(Order).where(Order.code == code)).first()
    if not o:
        return {"code": code, "status": "NOT_FOUND", "message": "سفارش با این کد یافت نشد."}
    return {"code": o.code, "status": o.status, "image": o.image_path}

@app.get("/u/{code}", response_class=HTMLResponse)
def track_page(code: str, request: Request, session: Session = Depends(get_session)):
    code = code.strip().upper()
    o = session.exec(select(Order).where(Order.code == code)).first()
    return templates.TemplateResponse("track.html", {"request": request, "order": o, "code": code})

# ======= آپلود دستی =======

@app.get("/manual", response_class=HTMLResponse)
def manual_form(request: Request):
    return templates.TemplateResponse("manual.html", {"request": request})

@app.post("/manual-attach")
def manual_attach(
    code: str = Form(...),
    status: str = Form("ARRIVED"),
    image: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    code = code.strip().upper()
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    o = session.exec(select(Order).where(Order.code == code)).first()
    if not o:
        o = Order(code=code)
        session.add(o); session.flush()

    o.image_path = rel_path
    o.status = status
    o.updated_at = datetime.utcnow()
    session.add(o); session.commit()

    return {"ok": True, "code": code, "status": o.status, "image": rel_path}

# ======= ingest (فعلاً بدون OCR؛ اگر OCR آماده است، اینجا صدا بزن) =======

@app.post("/ingest-image")
def ingest_image(
    image: UploadFile = File(...),
    hinted_code: str | None = Form(None),
    status: str | None = Form(None),
    session: Session = Depends(get_session)
):
    ext = Path(image.filename).suffix.lower() or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = Path("app/static/uploads") / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)
    rel_path = f"/static/uploads/{fname}"

    code = hinted_code.strip().upper() if hinted_code else None
    # اگر OCR داری:
    # if not code:
    #     code = detect_code_from_image(str(dest)) or None

    if not code:
        return {"ok": False, "needs_review": True, "image": rel_path, "message": "کد پیدا نشد."}

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
