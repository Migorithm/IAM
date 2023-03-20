import inspect
from typing import Type

# uow
from app.service_layer import unit_of_work


# handlers
from app.service_layer.messagebus import COMMAND_HANDLERS, EVENT_HANDLERS, MessageBus


class Bootstrap:
    def __init__(
        self,
        uow: Type[
            unit_of_work.SqlAlchemyUnitOfWork
        ] = unit_of_work.SqlAlchemyUnitOfWork,
    ):
        self.uow = uow

    def __call__(self):
        dependencies: dict = {}
        injected_event_handlers = {
            event_type: [
                inject_dependencies(handler, dependencies) for handler in event_handlers
            ]
            for event_type, event_handlers in EVENT_HANDLERS.items()
        }
        injected_command_handlers = {
            command_type: inject_dependencies(handler, dependencies)
            for command_type, handler in COMMAND_HANDLERS.items()
        }

        return MessageBus(
            uow=self.uow,
            event_handlers=injected_event_handlers,
            command_handlers=injected_command_handlers,
        )


def inject_dependencies(handler, dependencies: dict):
    params = inspect.signature(handler).parameters
    deps = {
        name: dependency for name, dependency in dependencies.items() if name in params
    }
    return lambda message: handler(message, **deps)
