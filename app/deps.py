from pathlib import Path
from typing import Dict, Any

from pydantic_settings import BaseSettings
from sqlmodel import SQLModel, Session, create_engine


class Settings(BaseSettings):
    # قابل تنظیم با Env یا .env
    DATABASE_URL: str = "sqlite:///./app.db"
    UPLOAD_DIR: str = "./app/static/uploads"
    BASE_URL: str = ""  # اختیاری

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# تنظیمات مخصوص SQLite برای عدم خطای Thread
connect_args: Dict[str, Any] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(engine)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


def get_session():
    with Session(engine) as session:
        yield session
