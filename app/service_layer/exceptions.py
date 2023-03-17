from typing import Any


class ObjectNotFound(Exception):
    pass


class StopSentinel(Exception):
    """
    Exception Raise For Error That Will Break Event Handlers
    """

    def __init__(self, message: str, event=None, result: Any = None) -> None:
        self.message = message
        self.event = event
        self.result = result
        super().__init__(self.message)
