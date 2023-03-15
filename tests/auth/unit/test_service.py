import pytest
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.future import select
from sqlalchemy.engine import Result
from app.domain import commands, iam, eventstore
from app.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from app.service_layer.handlers import IAMService


@pytest.mark.asyncio
async def test_create_user(session_factory: async_scoped_session):
    name = "Migo"
    email = "whatsoever@mail.com"
    cmd = commands.CreateUser(name=name, email=email)
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    await IAMService.create_user(msg=cmd, uow=uow)

    q: Result = await session_factory.execute(select(eventstore.EventStore))
    res = q.scalars().all()
    assert len(res) == 1
    rec = res[0]
    assert isinstance(rec, eventstore.EventStore)
    assert rec.id is not None
    assert rec.version == 1

    user: iam.User = await uow.users.get(rec.id)
    assert user.id == rec.id


@pytest.mark.skip("Impossible to succeed yet")
@pytest.mark.asyncio
async def test_create_group(session_factory: async_scoped_session):
    name = "Migo"
    email = "whatsoever@mail.com"
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    user_id = await IAMService.create_user(
        msg=commands.CreateUser(name=name, email=email), uow=uow
    )

    cmd = commands.RequestCreateGroup(name="SVB", user_id=user_id)
    await IAMService.request_create_group(msg=cmd, uow=uow)

    q: Result = await session_factory.execute(select(eventstore.EventStore))
    res = q.scalars().all()
    assert len(res) == 2
    assert isinstance(res[-1], eventstore.EventStore)

    user: iam.User = await uow.users.get(user_id)
    assert user.id == user_id


@pytest.mark.skip("Impossible to succeed yet")
def test_add_user_to_group():
    pass


@pytest.mark.skip("Impossible to succeed yet")
def test_delete_user_from_group():
    pass


@pytest.mark.skip("Impossible to succeed yet")
def test_assign_role_to_user():
    pass
