from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.settings import settings

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
