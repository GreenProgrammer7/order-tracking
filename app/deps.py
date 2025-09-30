from sqlmodel import create_engine, Session, SQLModel
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./dev.db"
    UPLOAD_DIR: str = "./app/static/uploads"
    BASE_URL: str = ""  # بعداً آدرس دامنه‌ات را می‌گذاری

settings = Settings()
engine = create_engine(settings.DATABASE_URL, echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

def get_session():
    with Session(engine) as s:
        yield s
