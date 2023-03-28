import logging
from collections import deque
from typing import Any, Callable, Type
from app.utils.events.domain_event import DomainEvent
from app.domain import commands
from app.domain.commands import Command
from app.service_layer import handlers
from .unit_of_work import SqlAlchemyUnitOfWork
from app.service_layer.exceptions import StopSentinel

logger = logging.getLogger(__name__)

Message = DomainEvent | Command


class MessageBus:
    def __init__(
        self,
        event_handlers: dict[Type[DomainEvent], list[Callable]],
        command_handlers: dict[Type[Command], Callable],
        uow: Type[SqlAlchemyUnitOfWork] = SqlAlchemyUnitOfWork,
    ):
        self.uow = uow
        self.event_handlers = event_handlers
        self.command_handlers = command_handlers

    async def handle(
        self, message: Message
    ) -> deque[Any]:  # Return type need to be specified?
        queue: deque = deque([message])
        uow = self.uow()
        results: deque = deque()
        while queue:
            message = queue.popleft()
            logger.info("handling message %s", message.__class__.__name__)
            match message:
                case DomainEvent():
                    await self.handle_event(message, queue, results, uow)
                case Command():
                    cmd_result = await self.handle_command(message, queue, uow)
                    results.append(cmd_result)
                case _:
                    logger.error(f"{message} was not an Event or Command")
                    raise Exception
        return results

    async def handle_event(
        self,
        event: DomainEvent,
        queue: deque,
        results: deque,
        uow: SqlAlchemyUnitOfWork,
    ):
        for handler in self.event_handlers[type(event)]:
            try:
                logger.debug("handling event %s with handler %s", event, handler)
                res = (
                    await handler(event, uow=uow)
                    if "uow" in handler.__code__.co_varnames
                    else await handler(event)
                )

                # Handle only internal backlogs that should be handled within the bounded context
                queue.extend(uow.collect_backlogs(in_out="internal_backlogs"))

                # Normally, event is not supposed to return result but when it must, resort to the following.
                if res:
                    results.append(res)
            except StopSentinel as e:
                logger.error("%s", str(e))

                # If failover strategy is implemented even is appended
                if e.event:
                    queue.append(e.event)

                # Break the loop upon the reception of stop sentinel
                break
            except Exception as error:
                logger.exception(f"exception while handling event {str(error)}")

    async def handle_command(
        self, command: Command, queue: deque, uow: SqlAlchemyUnitOfWork
    ):
        logger.debug("handling command %s", command)
        try:
            handler = self.command_handlers[type(command)]
            res = (
                await handler(command, uow=uow)
                if getattr(handler, "uow_required", False)
                else await handler(command)
            )
            queue.extend(uow.collect_backlogs(in_out="internal_backlogs"))
            return res
        except Exception as e:
            logger.exception(f"exception while handling command {str(e)}")
            raise e


EVENT_HANDLERS: dict = {}


COMMAND_HANDLERS: dict = {
    commands.CreateUser: handlers.IAMService.create_user,
    commands.RequestCreateGroup: handlers.IAMService.request_create_group,
}
