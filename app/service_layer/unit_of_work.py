from __future__ import annotations
from collections import deque
from typing import Generic, Literal

import weakref
from abc import ABC, abstractmethod
from asyncio import current_task

from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

from app.adapters.repository import EventStoreProxy, TAggregate, OutboxRepository
from app.db import async_transactional_session
from app.domain.outbox import OutBox


DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY = async_transactional_session


class AbstractUnitOfWork(Generic[TAggregate], ABC):
    users: EventStoreProxy
    groups: EventStoreProxy
    outboxes: OutboxRepository

    async def commit(self):
        await self._commit()

    async def rollback(self):
        await self._rollback()

    def collect_backlogs(
        self,
        in_out: Literal["internal_backlogs", "external_backlogs"] = "external_backlogs",
    ):
        # TODO sorting out externally_notifiable event VS event within a bounded context
        backlogs: deque
        while backlogs := getattr(self.users, in_out):
            yield backlogs.popleft()
        while backlogs := getattr(self.groups, in_out):
            yield backlogs.popleft()
        while backlogs := getattr(self.outboxes, in_out):
            yield backlogs.popleft()

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
        self.outboxes = OutboxRepository(model=OutBox, session=self.session)
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.rollback()
        await self.session.close()

    async def _commit(self):
        await self.session.commit()

    async def _rollback(self):
        await self.session.rollback()
