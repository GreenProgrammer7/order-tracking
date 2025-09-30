from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class OrderStatus:
    PENDING = "PENDING"   # هنوز نرسیده
    ARRIVED = "ARRIVED"   # رسیده (وقتی عکس بخوره)
    SHIPPED = "SHIPPED"   # ارسال شد

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    status: str = Field(default=OrderStatus.PENDING)
    image_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
