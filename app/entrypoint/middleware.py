from contextvars import ContextVar
from uuid import UUID
from fastapi import Request


class ContextWrapper:
    """
    Context Wrapper to wrap around the contextvar which will be used for
    managing session and request context.
    """

    def __init__(self, value: ContextVar):
        self.__value = value

    def set(self, value: UUID | Request):
        """
        Set value that's either UUID for db context or Request for request context.
        """
        return self.__value.set(value)

    def reset(self, token):
        self.__value.reset(token)
        return

    def __module__(self):
        return self.__value.get()

    @property
    def value(self):
        return self.__value.get()


request: ContextWrapper = ContextWrapper(ContextVar("request", default=None))
db: ContextWrapper = ContextWrapper(ContextVar("db", default=None))
