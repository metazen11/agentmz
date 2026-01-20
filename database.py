"""Database connection for v2 agentic system."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from env_utils import load_env


def get_database_url():
    """Construct database URL from environment variables."""
    # Prefer DATABASE_URL if set (used by Docker containers)
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL")

    # Fallback: Build from individual env vars
    user = os.getenv("POSTGRES_USER", "wfhub")
    password = os.getenv("POSTGRES_PASSWORD", "wfhub")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")  # v2 uses 5433 externally
    db = "agentic"  # Always use 'agentic' database for v2
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


load_env()
DATABASE_URL = get_database_url()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
