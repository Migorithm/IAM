import asyncio


import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_scoped_session,
)

from sqlalchemy.orm import clear_mappers, sessionmaker
from sqlalchemy import text
from app.adapters.orm import start_mappers, metadata
from app.adapters.eventstore import (
    start_mappers as start_es_mapper,
    metadata as es_metadata,
)

from app.config import db_settings


@pytest.fixture(scope="session", autouse=True)
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def aio_engine():
    engine: AsyncEngine = create_async_engine(db_settings.get_uri(), future=True)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(es_metadata.drop_all)
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(es_metadata.create_all)
    start_mappers()
    start_es_mapper()

    yield engine
    clear_mappers()


@pytest_asyncio.fixture(scope="function")
async def session_factory(aio_engine: AsyncEngine):
    async with aio_engine.connect() as conn:
        sf: sessionmaker = sessionmaker(
            conn,
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
        scoped_session = async_scoped_session(
            session_factory=sf, scopefunc=asyncio.current_task
        )
        yield scoped_session


@pytest_asyncio.fixture(scope="function")
async def session(session_factory: async_scoped_session):
    s: AsyncSession = session_factory()
    yield s

    for table in metadata.tables.keys():
        delete_stmt = f"DELETE FROM {table};"
        await s.execute(text(delete_stmt))
    for es_tb in es_metadata.tables.keys():
        delete_stmt = f"DELETE FROM {es_tb};"
        await s.execute(text(delete_stmt))

    await s.commit()
    await s.close()
