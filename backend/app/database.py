from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Create Connection Engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=100,
    max_overflow=50
)

# Thread-safe session generator
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """
    FastAPI Dependency yielding active transactional database sessions.
    Automatically closes session at the end of request lifecycle.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
