"""Database connection for v2 agentic system."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def get_database_url():
    """Construct database URL from environment variables."""
    # Build from individual env vars, always using 'agentic' database
    user = os.getenv("POSTGRES_USER", "wfhub")
    password = os.getenv("POSTGRES_PASSWORD", "wfhub")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = "agentic"  # Always use 'agentic' database for v2
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


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
