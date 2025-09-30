from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class OrderStatus:
    NOT_ARRIVED_DXB = "NOT_ARRIVED_DXB"   # هنوز به انبار دبی نرسیده
    ARRIVED_DXB     = "ARRIVED_DXB"       # رسیده به انبار دبی
    IN_TRANSIT_IR   = "IN_TRANSIT_IR"     # در مسیر ارسال به ایران
    ARRIVED_TEH     = "ARRIVED_TEH"       # رسیده به انبار تهران (به‌زودی ارسال می‌شود)

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)          # کد مشتری (که کاربر سرچ می‌کند)
    status: str = Field(default=OrderStatus.NOT_ARRIVED_DXB)
    image_path: Optional[str] = None                    # مسیر عکس بسته (در صورت وجود)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class OrderAlias(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_code: str = Field(index=True)                 # کد مشتری (اصلی)
    alias_code: str = Field(index=True, unique=True)    # کد روی بسته/اینویس/حامل
    carrier: Optional[str] = None                       # مثلا INVOICE / J&T / AJEX (اختیاری)
    created_at: datetime = Field(default_factory=datetime.utcnow)
