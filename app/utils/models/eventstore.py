from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(eq=False)
class EventStore:
    nt_id: int = field(init=False, repr=False)
    create_dt: datetime = field(init=False, repr=False)
    id: UUID
    version: int
    topic: str
    state: bytes

    def dict(self):
        return dict(
            nt_id=self.nt_id,
            id=self.id,
            version=self.version,
            topic=self.topic,
            state=self.state,
        )
