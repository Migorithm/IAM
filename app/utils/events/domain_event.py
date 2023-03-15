from datetime import datetime
from uuid import UUID

from . import meta


class DomainEvent(meta.ImmutableObject):
    id: UUID
    version: int
    timestamp: datetime
    notifiable: bool = False


class StoredEvent(meta.ImmutableObject):
    id: str
    version: int
    topic: str
    state: bytes  # Payload


class OutBoxEvent(meta.ImmutableObject):
    id: str
    version: int
    topic: str
    state: bytes
    processed: bool = False


class Notification(StoredEvent):
    nt_id: int
