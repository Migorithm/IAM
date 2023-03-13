from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    Numeric,
    Sequence,
    String,
    Table,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import registry

from app.domain.eventstore import EventStore

NUMERIC: Numeric = Numeric(19, 4)
metadata = MetaData()
mapper_registry = registry(metadata=metadata)


# Global sequence
EVENT_NT_SEQ: Sequence = Sequence("event_nt_seq", metadata=mapper_registry.metadata)

# Table Definition
event_store = Table(
    "iam_event_store",
    mapper_registry.metadata,
    Column(
        "nt_id",
        Integer,
        EVENT_NT_SEQ,
        server_default=EVENT_NT_SEQ.next_value(),
        primary_key=True,
    ),
    Column(
        "create_dt",
        postgresql.TIMESTAMP(timezone=True),
        default=func.now(),
        server_default=func.now(),
    ),
    Column("id", postgresql.UUID(as_uuid=True)),
    Column("version", Integer, nullable=False),
    Column("topic", String, nullable=False),
    Column("state", postgresql.BYTEA, nullable=False),
)

# Index on id, version
idx_on_event_store = Index(
    "idx_on_event_store", event_store.c.id, event_store.c.version, unique=True
)


def start_mappers():
    mapper_registry.map_imperatively(
        EventStore,
        event_store,
        eager_defaults=True,
    )
