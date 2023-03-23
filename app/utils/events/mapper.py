from __future__ import annotations

import json
from abc import ABC, abstractmethod
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, Mapping, Protocol, TypeVar, cast
from uuid import UUID

from asyncpg.pgproto import pgproto

from .meta import SignletonMeta

from .. import resolver
from .domain_event import DomainEvent, StoredEvent


# Protocols
class Cipher(Protocol):
    @staticmethod
    def encrypt(state):
        ...

    @staticmethod
    def decrypt(state):
        ...


class Compressor(Protocol):
    @staticmethod
    def compress(state):
        ...

    @staticmethod
    def decompress(state):
        ...


class AbstractTranscoder(ABC):
    """
    Abstract base class for transcoders
    """

    @abstractmethod
    def encode(self, o: Any) -> bytes:
        pass

    @abstractmethod
    def decode(self, d: bytes) -> Any:
        pass


class Transcoding(ABC):
    """
    Abstract base class for transcoding
    """

    type: type
    name: str

    @staticmethod
    @abstractmethod
    def encode(o: Any) -> str | dict:
        """
        Converts the object class to Python str for simple type or a Python dict for complex one.
        Converting to a dict may involve returning uncoverted custome types so they should be
        converted by their custom transcodings.
        """
        pass

    @staticmethod
    @abstractmethod
    def decode(d: str | dict) -> Any:
        pass


TTranscoding = TypeVar("TTranscoding", bound=Transcoding)


@dataclass
class Transcoder(Generic[TTranscoding], AbstractTranscoder):
    """
    Uses 'json' module to encode python objects as JSON strings that are encoded as UTF-8.
    Uses an extensible collection of transcoding objects to convert non-standard object types
    that cannot be handled by the JSON encoder and decoder to a particular python dict.

    The method encode() and decode() are used to encode and decode the state of domain event
    objects.
    """

    types: dict[type, Transcoding] = field(default_factory=dict)
    names: dict[str, Transcoding] = field(default_factory=dict)
    encoder: json.JSONEncoder = field(init=False)
    decoder: json.JSONDecoder = field(init=False)

    def __post_init__(self):
        self.encoder = json.JSONEncoder(default=self._encode_dict)
        self.decoder = json.JSONDecoder(object_hook=self._decode_dict)

    def _encode_dict(self, o: Any) -> dict[str, str | dict]:
        try:
            transcoding: Transcoding = self.types[type(o)]
        except KeyError:
            raise TypeError(
                f"Object of type {o.__class__.__name__} is not serializable!"
            )
        else:
            return {
                "__type__": transcoding.name,
                "__data__": transcoding.encode(o),
            }

    def _decode_dict(self, d: dict[str, str | dict]) -> Any:
        if set(d.keys()) == {"__type__", "__data__"}:
            t = d["__type__"]
            t = cast(str, t)
            transcoding = self.names[t]
            return transcoding.decode(d["__data__"])
        else:
            return d

    def register(self, transcoding: TTranscoding):
        self.types[transcoding.type] = transcoding
        self.names[transcoding.name] = transcoding

    def encode(self, o: Any) -> bytes:
        return self.encoder.encode(o).encode("utf8")

    def decode(self, d: bytes) -> Any:
        return self.decoder.decode(d.decode("utf8"))


transcoder: Transcoder = Transcoder()


@transcoder.register
class UUIDAsHex(Transcoding):
    type = UUID
    name = "uuid_hex"

    @staticmethod
    def encode(o: UUID) -> str:
        return o.hex

    @staticmethod
    def decode(d: str | dict) -> UUID:
        assert isinstance(d, str)
        return UUID(d)


@transcoder.register
class PgUUIDAsHex(Transcoding):
    type = pgproto.UUID
    name = "pguuid_hex"

    @staticmethod
    def encode(o: UUID) -> str:
        return o.hex

    @staticmethod
    def decode(d: str | dict) -> UUID:
        assert isinstance(d, str)
        return UUID(d)


@transcoder.register
class DecimalAsStr(Transcoding):
    type = Decimal
    name = "decimal_str"

    @staticmethod
    def encode(o: Decimal) -> str:
        return str(o)

    @staticmethod
    def decode(d: str | dict) -> Decimal:
        assert isinstance(d, str)
        return Decimal(d)


@transcoder.register
class DatetimeAsISO(Transcoding):
    type = datetime
    name = "datetime_iso"

    @staticmethod
    def encode(o: datetime) -> str:
        return o.isoformat()

    @staticmethod
    def decode(d: str | dict) -> datetime:
        assert isinstance(d, str)
        return datetime.fromisoformat(d)


# Mapper class
TDomainEvent = TypeVar("TDomainEvent", bound=DomainEvent)


@dataclass
class Mapper(Generic[TDomainEvent], metaclass=SignletonMeta):
    transcoder: AbstractTranscoder = field(init=False)
    cipher: Cipher | None = None
    compressor: Compressor | None = None

    def __post_init__(self):
        if not hasattr(self, "transcoder"):
            self.transcoder = transcoder

    def _convert_domain_event(
        self, domain_event: TDomainEvent
    ) -> tuple[UUID, int, str, bytes]:
        """
        Parses a domain event object returning id, version, topic, state
        """
        topic: str = resolver.get_topic(domain_event.__class__)
        d: dict = copy(domain_event.__dict__)
        _id = d.pop("id")
        _id = str(_id) if isinstance(_id, UUID) else _id
        _version = d.pop("version")

        state: bytes = self.transcoder.encode(d)

        if self.compressor:
            state = self.compressor.compress(state)
        if self.cipher:
            state = self.cipher.encrypt(state)
        return _id, _version, topic, state

    def _convert_stored_event(self, stored: StoredEvent) -> dict:
        state: bytes = stored.state
        if self.cipher:
            state = self.cipher.decrypt(state)
        if self.compressor:
            state = self.compressor.decompress(state)
        d = self.transcoder.decode(state)
        if isinstance(stored.id, str):
            d["id"] = UUID(stored.id)
        else:
            d["id"] = stored.id
        d["version"] = stored.version
        return d

    def from_domain_event_to_stored_event(
        self, domain_event: TDomainEvent
    ) -> StoredEvent:
        """
        Maps a domain event object to a new stored event object
        """
        _id, _version, topic, state = self._convert_domain_event(domain_event)

        return StoredEvent(  # type: ignore
            id=_id,
            version=_version,
            topic=topic,
            state=state,
        )

    def from_stored_event_to_domain_event(self, stored: StoredEvent) -> TDomainEvent:
        """
        Maps a stored event object to a new domain event object
        """
        dictified_state = self._convert_stored_event(stored)
        cls = resolver.resolve_topic(stored.topic)
        assert issubclass(cls, DomainEvent)
        domain_event: TDomainEvent = object.__new__(cls)
        return domain_event.from_kwargs(**dictified_state)

    def take_event(self, decodable: Mapping) -> dict:
        try:
            d: dict = self.transcoder.decode(decodable["state"])
            d["id"] = decodable.get("aggregate_id")
            cls = resolver.resolve_topic(decodable["topic"])
            event_cls: TDomainEvent = object.__new__(cls)
            event = event_cls.from_kwargs(**d)

        except KeyError:
            print("'state' doesn't exist!")
        return event
