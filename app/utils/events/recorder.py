from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from sqlalchemy import insert, text
from sqlalchemy.engine import Result

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.eventstore import EventStore
from .domain_event import Notification, StoredEvent


class Recorder(ABC):
    class OperationalError(Exception):
        pass

    class IntegrityError(Exception):
        pass


class AggregateRecorder(Recorder):
    @abstractmethod
    async def add(self, stored_events: list[StoredEvent], **kwargs) -> None:
        """
        Writes stored events into database
        """

    @abstractmethod
    async def get(
        self,
        aggregate_id: UUID,
        # TODO condition
        # gt: int|None = None,
        # lte: int|None = None,
        # desc: bool|None = False,
        # limit: int|None =None
    ) -> list[StoredEvent]:
        """
        Reads stored events from database
        """


class PostgresAggregateRecorder(Recorder):
    def __init__(self, session: AsyncSession, application_name: str = "trrk") -> None:
        self.session = session
        self.application_name = application_name
        self.events_table = application_name.lower() + "_events"

    async def add(self, stored_events: list[StoredEvent], **kwargs) -> None:
        await self._insert_events(stored_events, **kwargs)

    async def _insert_events(self, stored_events: list[StoredEvent], **kwargs) -> None:
        try:
            await self.session.execute(
                insert(EventStore),
                [e.__dict__ for e in stored_events],
            )
        except Exception as e:
            raise self.IntegrityError(e)

    async def get(
        self,
        aggregate_id: UUID,
        # gt: int | None = None,
        # lte: int | None = None,
        # desc: bool | None = False,
        # limit: int | None = None
    ) -> list[StoredEvent]:
        # TODO need to add conditions
        c: Result = await self.session.execute(
            select(EventStore).where(EventStore.id == aggregate_id)  # type: ignore
        )

        stored_events = [
            StoredEvent.from_kwargs(**row.dict()) for row in c.scalars().all()
        ]

        return stored_events


class PostgresApplicationRecorder(PostgresAggregateRecorder):
    async def select_notifications(self, start: int, limit: int) -> list[Notification]:
        stmt = (
            select(EventStore)  # type: ignore
            .where(EventStore.nt_id >= start)  # type: ignore
            .order_by(EventStore.nt_id)
            .limit(limit=limit)
        )
        q: Result = await self.session.execute(stmt)
        return [Notification(**e.__dict__) for e in q.scalars().all()]

    async def max_notification_id(self) -> int:
        """
        Returns the maximum notification id -> nt_id
        """
        stmt = text(f"SELECT MAX(nt_id) FROM {self.events_table}")
        q = await self.session.execute(stmt)

        return q.scalar_one_or_none() or 0


class ApplicationRecorder(Protocol):
    async def add(self, stored_events: list[StoredEvent], **kwargs) -> None:
        ...

    async def get(
        self,
        aggregate_id: UUID,
        # TODO condition
        # gt: int|None = None,
        # lte: int|None = None,
        # desc: bool|None = False,
        # limit: int|None =None
    ) -> list[StoredEvent]:
        ...

    async def select_notifications(self, start: int, limit: int):
        ...

    async def max_notification_id(self):
        ...
