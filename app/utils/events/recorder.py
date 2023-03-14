from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from sqlalchemy import text


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
    def __init__(
        self, session: AsyncSession, event_table_name: str = "iam_event_store"
    ) -> None:
        self.session = session

        self.events_table = event_table_name

    async def add(self, stored_events: list[StoredEvent], **kwargs) -> None:
        await self._insert_events(stored_events, **kwargs)

    async def _insert_events(self, stored_events: list[StoredEvent], **kwargs) -> None:
        keys = tuple(stored_events[0].__dict__.keys())
        raw_query = text(
            f"""
            INSERT INTO {self.events_table} ({",".join(keys)})
            VALUES ({",".join((":"+k for k in keys))})
        """
        )
        try:
            await self.session.execute(
                raw_query,
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
        raw_query = text(
            f"""
            SELECT * FROM {self.events_table}
            WHERE id = :id
        """
        )
        c = await self.session.execute(raw_query, dict(id=aggregate_id))

        stored_events = [
            StoredEvent.from_kwargs(**row._mapping) for row in c.fetchall()
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
        q = await self.session.execute(stmt)
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
