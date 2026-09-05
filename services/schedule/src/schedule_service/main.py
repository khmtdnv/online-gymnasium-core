from schedule_service.app import create_app
from schedule_service.config import Settings
from schedule_service.infrastructure.database import create_engine

settings = Settings()
engine = create_engine(settings.database_url)
app = create_app(settings, engine)
