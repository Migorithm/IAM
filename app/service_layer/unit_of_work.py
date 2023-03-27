from __future__ import annotations
from collections import deque
from typing import Generic, Literal

import weakref
from abc import ABC, abstractmethod
from asyncio import current_task

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    create_async_engine,
)

from app.adapters.repository import EventRepositoryProxy, TAggregate, OutboxRepository
from app.domain.outbox import OutBox
from sqlalchemy.orm import sessionmaker
from app import config


class AbstractUnitOfWork(Generic[TAggregate], ABC):
    users: EventRepositoryProxy
    groups: EventRepositoryProxy
    outboxes: OutboxRepository

    async def commit(self):
        self._commit_hook()
        await self._commit()

    def _commit_hook(self):
        pass

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


engine = create_async_engine(
    config.db_settings.get_uri(),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)
async_transactional_session = async_scoped_session(
    sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    scopefunc=current_task,
)
autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")

async_autocommit_session = async_scoped_session(
    sessionmaker(autocommit_engine, expire_on_commit=False, class_=AsyncSession),
    scopefunc=current_task,
)

DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY = async_transactional_session


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=None):
        self.session_factory = (
            DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY
            if session_factory is None
            else session_factory
        )

    async def __aenter__(self):
        self.session: AsyncSession = self.session_factory()
        self.event_store: EventRepositoryProxy = EventRepositoryProxy(
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

    def _commit_hook(self):
        # TODO Test
        for outbox in self.collect_backlogs(in_out="external_backlogs"):
            self.outboxes.add(outbox)

    async def _rollback(self):
        await self.session.rollback()
