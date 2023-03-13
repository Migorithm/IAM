from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from . import config

engine = create_async_engine(
    config.db_settings.get_uri(),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)
async_transactional_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")

async_autocommit_session = sessionmaker(
    autocommit_engine, expire_on_commit=False, class_=AsyncSession
)
