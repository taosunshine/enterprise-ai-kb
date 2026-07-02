import psycopg
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria

from app.core.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "do_orm_execute")
def hide_soft_deleted_records(execute_state):
    if execute_state.is_select and not execute_state.execution_options.get("include_deleted"):
        from app.models import ChunkEmbedding, Document, DocumentChunk, KnowledgeBase

        execute_state.statement = execute_state.statement.options(
            *(
                with_loader_criteria(
                    model,
                    lambda entity: entity.deleted_at.is_(None),
                    include_aliases=True,
                )
                for model in (KnowledgeBase, Document, DocumentChunk, ChunkEmbedding)
            )
        )


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
