from datetime import datetime
from uuid import UUID

from . import meta


class DomainEvent(meta.ImmutableObject):
    id: UUID
    version: int
    timestamp: datetime


class StoredEvent(meta.ImmutableObject):
    id: str
    version: int
    topic: str
    state: bytes  # Payload


class Notification(StoredEvent):
    nt_id: int
