import asyncio
import pytest
from app.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from app.service_layer.messagebus import MessageBus
from app.service_layer.handlers import ServiceMeta
from app.domain.commands import Command
from app.utils.events.domain_event import DomainEvent

from tests.fakes import f


@pytest.mark.asyncio
async def test_messagebus():
    # When
    class TestCommand(Command):
        pass

    class TestEvent(DomainEvent):
        pass

    class FakeService(metaclass=ServiceMeta):
        @classmethod
        async def test_command(cls, msg: TestCommand, *, uow: SqlAlchemyUnitOfWork):
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

    event_handlers = {TestEvent: [FakeService.test_event]}
    commands_handlers = {TestCommand: FakeService.test_command}
    bus = MessageBus(
        uow=SqlAlchemyUnitOfWork,
        event_handlers=event_handlers,
        command_handlers=commands_handlers,
    )

    res = await bus.handle(TestCommand())

    # Then
    assert res
    assert isinstance(next(r for r in res), TestCommand)


@pytest.mark.skip("TODO")
@pytest.mark.asyncio
async def test_message_bus_stop_looping_upon_reception_of_sentinel():
    ...
