from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.utils.events.mapper import Mapper
from app.utils.events.recorder import (
    ApplicationRecorder,
    PostgresApplicationRecorder,
)
from app.utils.models import aggregate_root


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


TAggregate = TypeVar("TAggregate", bound=aggregate_root.Aggregate)


class AbstractSqlAlchemyRepository(AbstractRepository):
    pass


class SqlAlchemyRepository(Generic[TAggregate], AbstractSqlAlchemyRepository):
    def __init__(self, model: TAggregate, session: AsyncSession):
        self.seen: set[TAggregate] = set()
        self.model = model
        self.session = session
        self._base_query = select(self.model)

    def _add(self, *obj):
        self.session.add_all(obj)

    def _add_hook(self, *obj):
        self.seen.add(*obj)

    async def _get(self, ref: str | UUID) -> aggregate_root.Aggregate | None:
        reference = str(ref) if isinstance(ref, UUID) else ref
        q = await self.session.execute(
            self._base_query.where(getattr(self.model, "id") == reference).limit(1)
        )

        return q.scalars().first()

    def _get_hook(self, aggregate):
        if aggregate:
            self.seen.add(aggregate)

    async def _list(self):
        q = await self.session.execute(self._base_query)
        return q.scalars().all()


class EventStoreProxy(AbstractSqlAlchemyRepository):
    def __init__(
        self, *, session: AsyncSession, recorder: ApplicationRecorder | None = None
    ):
        self.mapper: Mapper[aggregate_root.Aggregate.Event] = Mapper()
        self.recorder: ApplicationRecorder = (
            PostgresApplicationRecorder(session=session)
            if recorder is None
            else recorder
        )

    async def _add(self, *aggregate: aggregate_root.Aggregate, **kwargs) -> None:
        pending_events = []
        for agg in aggregate:
            pending_events += list(agg._collect_())
        await self.recorder.add(
            list(map(self.mapper.from_domain_event, pending_events)), **kwargs
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
