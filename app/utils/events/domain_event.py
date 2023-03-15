from datetime import datetime
from uuid import UUID

from . import meta


class DomainEvent(meta.ImmutableObject):
    id: UUID
    version: int = 0
    timestamp: datetime
    notifiable: bool = False


class StoredEvent(meta.ImmutableObject):
    id: str
    version: int
    topic: str
    state: bytes  # Payload


class OutBoxEvent(meta.ImmutableObject):
    aggregate_id: str
    topic: str
    state: bytes
    processed: bool = False


class Notification(StoredEvent):
    nt_id: int
