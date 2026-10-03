from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

db_url = settings.DATABASE_URL.strip() if settings.DATABASE_URL else "sqlite:///./agent_hub.db"
is_sqlite = "sqlite" in db_url

connect_args = {"check_same_thread": False} if is_sqlite else {
    "connect_timeout": 20,
    "read_timeout": 30,
    "write_timeout": 30
}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=60 if not is_sqlite else -1,
    pool_size=10 if not is_sqlite else 5,
    max_overflow=20 if not is_sqlite else 10,
    pool_timeout=30
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
