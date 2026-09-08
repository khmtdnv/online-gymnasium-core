from schedule_service.app import create_app
from schedule_service.config import Settings
from schedule_service.infrastructure.database import create_engine, create_session_factory
from schedule_service.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

settings = Settings()
engine = create_engine(settings.database_url)
session_factory = create_session_factory(engine)

app = create_app(
    settings,
    engine,
    uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
)
