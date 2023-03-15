from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Generic, Protocol, Sequence, TypeVar
from uuid import UUID
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.engine.row import RowMapping
from app.utils import resolver
from app.utils.events.mapper import Mapper, transcoder, TDomainEvent
from app.utils.events.recorder import (
    PostgresAggregateRecorder,
)
from app.adapters.eventstore import event_store
from app.utils.models import aggregate_root
from app.domain.outbox import OutBox


TAggregate = TypeVar("TAggregate", bound=aggregate_root.Aggregate)


class ApplicationRecorder(Protocol):
    @property
    def outbox_table(self) -> str:
        ...

    @property
    def events_table(self) -> str:
        ...

    async def add(self, stored_events: Sequence[Any], **kwargs) -> None:
        ...

    async def get(
        self,
        aggregate_id: UUID,
        # TODO condition
        # gt: int|None = None,
        # lte: int|None = None,
        # desc: bool|None = False,
        # limit: int|None =None
    ) -> list[Any]:
        ...


class AbstractRepository(ABC):
    """Abstract Repository For Abstracting Persistence Layer"""

    def add(self, *obj):
        self._add_hook(*obj)
        return self._add(*obj)

    def _add_hook(self, *obj):
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
    def _add(self, *obj):
        raise NotImplementedError

    # @abstractmethod
    async def _list(self):
        raise NotImplementedError

    @abstractmethod
    async def _get(self, ref):
        raise NotImplementedError


class AbstractSqlAlchemyRepository(AbstractRepository):
    pass


class SqlAlchemyRepository(Generic[TAggregate], AbstractSqlAlchemyRepository):
    def __init__(self, model: TAggregate, session: AsyncSession):
        self.backlogs: deque = deque()
        self.model = model
        self.session = session
        self._base_query = select(self.model)

    def _add(self, *obj):
        self.session.add_all(obj)

    def _add_hook(self, *obj: TAggregate):
        for o in obj:
            self.backlogs.extend(filter(lambda e: e.notifiable, o.events))

    async def _get(self, ref: str | UUID) -> aggregate_root.Aggregate | None:
        reference = str(ref) if isinstance(ref, UUID) else ref
        q = await self.session.execute(
            self._base_query.where(getattr(self.model, "id") == reference).limit(1)
        )

        return q.scalars().first()

    async def _list(self):
        q = await self.session.execute(self._base_query)
        return q.scalars().all()


class OutboxRepository(SqlAlchemyRepository, Generic[TDomainEvent]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transcoder = transcoder

    async def _list(self):
        raw_query = text(
            f"""
        SELECT * FROM {self.model.__table__.name} 
        WHERE processed is false
        """
        )
        q = await self.session.execute(raw_query)

        return [
            OutBox(event=self.take_event(row._mapping), **row._mapping)
            for row in q.fetchall()
        ]

    def take_event(self, decodable: RowMapping) -> dict:
        try:
            d: dict = self.transcoder.decode(decodable["state"])
            d["id"] = decodable.get("aggregate_id")
            cls = resolver.resolve_topic(decodable["topic"])
            event_cls: TDomainEvent = object.__new__(cls)
            event = event_cls.from_kwargs(**d)

        except KeyError:
            print("'state' doesn't exist!")
        return event


class EventStoreProxy(AbstractSqlAlchemyRepository):
    def __init__(
        self, *, session: AsyncSession, recorder: ApplicationRecorder | None = None
    ):
        self.mapper: Mapper[aggregate_root.Aggregate.Event] = Mapper()
        self.recorder: ApplicationRecorder = (
            PostgresAggregateRecorder(
                session=session, event_table_name=event_store.name
            )
            if recorder is None
            else recorder
        )
        self.backlogs: deque = deque()

    def _add_hook(self, *obj: TAggregate):
        for o in obj:
            self.backlogs.extend(filter(lambda e: e.notifiable, o.events))

    async def _add(self, *aggregate: TAggregate, **kwargs) -> None:
        pending_events = []
        for agg in aggregate:
            pending_events += list(agg._collect_())

        # To Outbox
        await self.recorder.add(
            tuple(
                map(
                    self.mapper.from_domain_event_to_outbox,
                    filter(lambda x: x.notifiable, pending_events),
                )
            ),
            tb_name=self.recorder.outbox_table,
            **kwargs,
        )

        # To Aggregate
        await self.recorder.add(
            tuple(map(self.mapper.from_domain_event, pending_events)), **kwargs
        )

    async def _get(
        self,
        aggregate_id: UUID,
    ) -> aggregate_root.Aggregate:
        aggregate = None

        for domain_event in map(
            self.mapper.to_domain_event,
            await self.recorder.get(aggregate_id=aggregate_id),
        ):
            aggregate = domain_event.mutate(aggregate)
        if aggregate is None:
            raise self.AggregateNotFoundError
        assert isinstance(aggregate, aggregate_root.Aggregate)
        return aggregate

    class AggregateNotFoundError(Exception):
        pass
