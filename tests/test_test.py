from asyncio import sleep, create_task, gather
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


def test_sync_test_work():
    assert 1 == 1


@pytest.mark.asyncio
async def test_async_test_work():
    await sleep(0)
    assert 1 == 1


@pytest.mark.asyncio
async def test_async_session(session: AsyncSession):
    q = await session.execute(text("SELECT 1"))
    a = q.scalar_one()
    assert a == 1


async def async_work_for_test(session: AsyncSession, num: int):
    q = await session.execute(text("SELECT {}".format(num)))
    return q.scalar_one()


@pytest.mark.asyncio
async def test_async_operation_session(session: AsyncSession):
    t1 = create_task(async_work_for_test(session, 1))
    t2 = create_task(async_work_for_test(session, 2))
    t3 = create_task(async_work_for_test(session, 3))
    a, b, c = await gather(t1, t2, t3)
    assert a == 1
    assert b == 2
    assert c == 3
