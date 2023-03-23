from abc import ABC, abstractmethod
from collections import deque
from typing import Generic, Sequence, TypeVar
from uuid import UUID, uuid4
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.engine.cursor import CursorResult
from app.utils.events.domain_event import StoredEvent
from app.utils.events.mapper import Mapper
from app.adapters.eventstore import event_store
from app.utils.models import aggregate_root
from app.domain.outbox import OutBox


TAggregate = TypeVar("TAggregate", bound=aggregate_root.Aggregate)


class AbstractRepository(ABC):
    """Abstract Repository For Abstracting Persistence Layer"""

    def add(self, *obj, **kwargs):
        self._add_hook(*obj, **kwargs)
        return self._add(*obj, **kwargs)

    def _add_hook(self, *obj, **kwargs):
        pass

    async def get(self, ref: str | UUID, **kwargs):
        res = await self._get(ref)
        self._get_hook(res)
        return res

    def _get_hook(self, aggregate):
        pass

    async def list(self):
        res = await self._list()
        return res

    @abstractmethod
    def _add(self, *obj, **kwargs):
        raise NotImplementedError

    # @abstractmethod
    async def _list(self):
        raise NotImplementedError

    @abstractmethod
    async def _get(self, ref):
        raise NotImplementedError

    class OperationalError(Exception):
        pass

    class IntegrityError(Exception):
        pass

    class AggregateNotFoundError(Exception):
        pass


class AbstractSqlAlchemyRepository(AbstractRepository):
    pass


class SqlAlchemyRepository(Generic[TAggregate], AbstractSqlAlchemyRepository):
    def __init__(self, model: TAggregate, session: AsyncSession):
        self.model = model
        self.session = session
        self._base_query = select(self.model)
        self.external_backlogs: deque[aggregate_root.Aggregate.Event] = deque()
        self.internal_backlogs: deque[aggregate_root.Aggregate.Event] = deque()
        self.mapper: Mapper[aggregate_root.Aggregate.Event] = Mapper()

    def _add(self, *obj):
        self.session.add_all(obj)

    def _add_hook(self, *obj: TAggregate):
        """
        Filter out exportable events, inserts them to external_backlogs
        """
        for o in obj:
            self.external_backlogs.extend(
                filter(lambda e: e.externally_notifiable, o.events)
            )

    async def _get(self, ref: str | UUID) -> aggregate_root.Aggregate | None:
        reference = str(ref) if isinstance(ref, UUID) else ref
        q: CursorResult = await self.session.execute(
            self._base_query.where(getattr(self.model, "id") == reference).limit(1)
        )

        return q.scalars().first()

    async def _list(self):
        q: CursorResult = await self.session.execute(self._base_query)
        return q.scalars().all()


class OutboxRepository(SqlAlchemyRepository):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _add(self, *obj: aggregate_root.Aggregate.Event):
        """
        Map the obj to Outbox
        """
        for domain_event in obj:
            _id, _, topic, state = self.mapper._convert_domain_event(domain_event)
            self.session.add(
                OutBox(id=uuid4(), aggregate_id=_id, topic=topic, state=state)
            )

    async def _list(self):
        raw_query = text(
            f"""
        SELECT * FROM {self.model.__table__.name} 
        WHERE processed is false
        """
        )
        q: CursorResult = await self.session.execute(raw_query)

        return [
            OutBox(event=self.mapper.take_event(row._mapping), **row._mapping)
            for row in q.fetchall()
        ]


class EventStoreRepository(AbstractSqlAlchemyRepository):
    def __init__(
        self,
        session: AsyncSession,
        event_table_name: str = "iam_event_store",
    ) -> None:
        self.session = session

        self._events_table = event_table_name

    async def _add(self, stored_events: Sequence[StoredEvent], **kwargs) -> None:
        await self._insert_events(stored_events)

    async def _insert_events(
        self,
        events: Sequence[StoredEvent],
        *,
        tb_name: str | None = None,
        **kwargs,
    ) -> None:
        if len(events) == 0:
            return

        tb_name = self._events_table if tb_name is None else tb_name
        keys = tuple(events[0].__dict__.keys())

        raw_query = text(
            f"""
            INSERT INTO {tb_name} ({",".join(keys)})
            VALUES ({",".join((":"+k for k in keys))})
        """
        )
        try:
            await self.session.execute(
                raw_query,
                [e.__dict__ for e in events],
            )
        except Exception as e:
            raise self.IntegrityError(e)

    async def _get(
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
            SELECT * FROM {self._events_table}
            WHERE id = :id
        """
        )
        c: CursorResult = await self.session.execute(raw_query, dict(id=aggregate_id))

        stored_events = [
            StoredEvent.from_kwargs(**row._mapping) for row in c.fetchall()
        ]

        return stored_events


class EventStoreProxy(AbstractSqlAlchemyRepository):
    def __init__(self, *, session: AsyncSession):
        self.mapper: Mapper[aggregate_root.Aggregate.Event] = Mapper()
        self.recorder: EventStoreRepository = EventStoreRepository(
            session=session, event_table_name=event_store.name
        )
        self.external_backlogs: deque[aggregate_root.Aggregate.Event] = deque()
        self.internal_backlogs: deque[aggregate_root.Aggregate.Event] = deque()

    def _add_hook(self, *obj: TAggregate):
        for o in obj:
            self.external_backlogs.extend(
                filter(lambda e: e.externally_notifiable, o.events)
            )
            self.internal_backlogs.extend(
                filter(lambda e: e.internally_notifiable, o.events)
            )

    async def _add(self, *aggregate: TAggregate, **kwargs) -> None:
        pending_events = []
        for agg in aggregate:
            pending_events += list(agg._collect_())

        # To Aggregate
        await self.recorder.add(
            tuple(map(self.mapper.from_domain_event_to_stored_event, pending_events)),
            **kwargs,
        )

    async def _get(
        self,
        aggregate_id: UUID,
    ) -> aggregate_root.Aggregate:
        aggregate = None

        for domain_event in map(
            self.mapper.from_stored_event_to_domain_event,
            await self.recorder.get(aggregate_id),
        ):
            aggregate = domain_event.mutate(aggregate)
        if aggregate is None:
            raise self.AggregateNotFoundError
        assert isinstance(aggregate, aggregate_root.Aggregate)
        return aggregate
