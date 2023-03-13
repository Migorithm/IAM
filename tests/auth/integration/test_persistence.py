import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters import eventstore
from app.adapters import orm


@pytest.mark.asyncio
async def test_get_table_and_view_names(aio_engine: AsyncEngine):
    def get_table_names(conn):
        inspector = inspect(conn)
        return inspector.get_table_names()

    def get_view_names(conn):
        inspector = inspect(conn)

        return inspector.get_view_names()

    async with aio_engine.connect() as connection:
        table_names = await connection.run_sync(get_table_names)
        for auth_table in orm.metadata.tables.keys():
            assert auth_table in table_names

        for es_obj in eventstore.metadata.tables.keys():
            assert es_obj in table_names
