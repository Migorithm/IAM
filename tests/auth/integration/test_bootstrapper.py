import asyncio
import pytest
from app.bootstrap import Bootstrap
from app.service_layer.handlers import ServiceMeta
from app.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from app.domain.commands import Command
from app.utils.events.domain_event import DomainEvent
from tests.fakes import f


@pytest.mark.asyncio
async def test_bootstrapper():
    # GIVEN
    def injectable_func():
        return True

    class TestCommand(Command):
        pass

    class TestEvent(DomainEvent):
        pass

    class FakeService(metaclass=ServiceMeta):
        @classmethod
        async def test_command(
            cls, msg: TestCommand, *, uow: SqlAlchemyUnitOfWork, injected_func
        ):
            # THEN
            assert injected_func()

            async with uow:
                uow.users.internal_backlogs.append(
                    TestEvent(
                        id=f.uuid4(),
                        timestamp=f.date_time(),
                        internally_notifiable=True,
                    )
                )
                return msg

        @classmethod
        async def test_event(cls, msg: TestEvent, *, uow: SqlAlchemyUnitOfWork):
            print(msg)
            await asyncio.sleep(0)

    bootstrap = Bootstrap(
        command_handlers={TestCommand: FakeService.test_command},
        event_handlers={TestEvent: [FakeService.test_event]},
        injected_func=injectable_func,
    )

    # WHEN
    bus = bootstrap()

    # THEN
    res = await bus.handle(TestCommand())
    assert res
    assert isinstance(next(r for r in res), TestCommand)
