from __future__ import annotations

import inspect
from dataclasses import dataclass
from threading import Lock


class EventMetaclass(type):
    def __new__(cls, *args, **kwargs):
        new_cls = super().__new__(cls, *args, **kwargs)
        return dataclass(frozen=True, kw_only=True)(new_cls)


class ImmutableObject(metaclass=EventMetaclass):
    @classmethod
    def from_kwargs(cls, **kwargs):
        annots = inspect.get_annotations(cls.__init__)
        _kwargs = dict()
        for k, v in kwargs.items():
            if k in annots:
                _kwargs[k] = v
        return cls(**_kwargs)


class SignletonMeta(type):
    _instances: dict = {}
    _lock: Lock = Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]
