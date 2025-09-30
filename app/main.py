from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlmodel import select, Session
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates

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
