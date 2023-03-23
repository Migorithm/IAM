from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from typing import Protocol


class Event(Protocol):
    ...


@dataclass(eq=False)
class OutBox:
    create_dt: datetime = field(init=False, repr=False)
    id: UUID
    aggregate_id: UUID
    topic: str
    state: dict | bytes
    processed: bool = False
    event: Event | None = None

    def dict(self):
        return dict(
            id=self.id,
            topic=self.topic,
            state=self.state,
            processed=self.processed,
        )
