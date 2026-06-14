import psycopg
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("postgresql"):
    @event.listens_for(engine, "connect")
    def register_vector(dbapi_connection, _):
        from pgvector.psycopg import register_vector

        try:
            register_vector(dbapi_connection)
        except psycopg.ProgrammingError:
            # Fresh databases create the extension during initialization.
            pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
