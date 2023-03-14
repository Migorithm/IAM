from __future__ import annotations
from typing import Generic

import weakref
from abc import ABC, abstractmethod
from asyncio import current_task

from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

from app.adapters.repository import EventStoreProxy, TAggregate
from app.db import async_transactional_session


DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY = async_transactional_session


class AbstractUnitOfWork(Generic[TAggregate], ABC):
    users: EventStoreProxy
    groups: EventStoreProxy

    async def commit(self):
        await self._commit()

    async def rollback(self):
        await self._rollback()

    # def collect_new_events(self):
    #     for obj in self.users.seen:
    #         while obj.events:
    #             yield obj.events.popleft()

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.rollback()

    @abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abstractmethod
    async def _rollback(self):
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=None):
        self.session_factory = (
            DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY
            if session_factory is None
            else session_factory
        )

    async def __aenter__(self):
        self.session: AsyncSession = async_scoped_session(
            session_factory=self.session_factory,
            scopefunc=current_task,
        )()
        self.event_store: EventStoreProxy = EventStoreProxy(
            session=self.session,
        )

        self.users = weakref.proxy(self.event_store)
        self.groups = weakref.proxy(self.event_store)

        return await super().__aenter__()

    async def __aexit__(self, *args, **kwargs):
        await super().__aexit__(*args, **kwargs)
        await self.session.close()

    async def _commit(self):
        await self.session.commit()

    async def _rollback(self):
        await self.session.rollback()
