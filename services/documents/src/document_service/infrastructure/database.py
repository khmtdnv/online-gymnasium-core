from sqlalchemy import Engine
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine(url: str) -> Engine:
    return create_sync_engine(url)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)
