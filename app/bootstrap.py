from functools import partial
import inspect
from typing import Callable, Type
from copy import copy

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
        event_handlers: dict | None = None,
        command_handlers: dict | None = None,
        **kwargs,  # accept kwargs for testability
    ):
        self.uow = uow

        self.event_handlers = (
            event_handlers if event_handlers is not None else copy(EVENT_HANDLERS)
        )
        self.command_handlers = (
            command_handlers if command_handlers is not None else copy(COMMAND_HANDLERS)
        )
        self.dependencies = {k: v for k, v in kwargs.items()}

    def __call__(self):
        # dependencies: dict = {}
        injected_event_handlers = {
            event_type: [
                inject_dependencies(handler, self.dependencies)
                for handler in listed_handlers
            ]
            for event_type, listed_handlers in self.event_handlers.items()
        }
        injected_command_handlers = {
            command_type: inject_dependencies(handler, self.dependencies)
            for command_type, handler in self.command_handlers.items()
        }

        return MessageBus(
            uow=self.uow,
            event_handlers=injected_event_handlers,
            command_handlers=injected_command_handlers,
        )


def inject_dependencies(handler, dependencies: dict) -> Callable:
    params = inspect.signature(handler).parameters
    deps = {
        name: dependency for name, dependency in dependencies.items() if name in params
    }

    # Create function dynamically
    return render_injected_function(handler=handler, **deps)


def render_injected_function(handler, **kwrags) -> Callable:
    func = partial(handler, **kwrags)
    setattr(func, "uow_required", handler.uow_required)
    return func
