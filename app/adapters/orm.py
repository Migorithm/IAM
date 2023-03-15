from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Boolean,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import registry, relationship
from app.domain import iam
from app.domain import outbox

metadata = MetaData()
mapper_registry = registry(metadata=metadata)

users = Table(
    "iam_service_user",
    mapper_registry.metadata,
    Column("create_dt", postgresql.TIMESTAMP(timezone=True)),
    Column("update_dt", postgresql.TIMESTAMP(timezone=True)),
    Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column("name", String),
    Column("email", String),
    Column("email_verified", Boolean, server_default="false"),
    Column("permissions", Integer, nullable=False),
)

groups = Table(
    "iam_service_group",
    mapper_registry.metadata,
    Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column("name", String),
    Column("permissions", Integer, nullable=False),
)

group_roles = Table(
    "iam_service_group_role",
    mapper_registry.metadata,
    Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column("group_id", ForeignKey(groups.name + ".id", ondelete="cascade"), index=True),
    Column("name", String),
    Column("permissions", Integer, nullable=False),
)

group_role_user_associations = Table(
    "iam_service_group_role_user_association",
    mapper_registry.metadata,
    Column("user_id", ForeignKey(users.name + ".id"), primary_key=True),
    Column("group_role_id", ForeignKey(group_roles.name + ".id"), primary_key=True),
)

outboxes = Table(
    "iam_service_outbox",
    mapper_registry.metadata,
    Column(
        "create_dt",
        postgresql.TIMESTAMP(timezone=True),
        default=func.now(),
        server_default=func.now(),
    ),
    Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("aggregate_id", postgresql.UUID(as_uuid=True)),
    Column("topic", String, nullable=False),
    Column("state", postgresql.BYTEA, nullable=False),
    Column("processed", Boolean, server_default="f"),
)


def start_mappers():
    mapper_registry.map_imperatively(
        iam.User,
        users,
        properties={
            "group_roles": relationship(
                iam.GroupRoles,
                back_populates="users",
                secondary=group_role_user_associations,
                primaryjoin=f"{users.name}.c.id=={group_role_user_associations.name}.c.user_id",
                secondaryjoin=f"{group_role_user_associations.name}.c.group_role_id=={group_roles.name}.c.id",
                uselist=True,
                collection_class=set,
                innerjoin=True,
            ),
        },
        eager_defaults=True,
    )

    mapper_registry.map_imperatively(
        iam.GroupRoles,
        group_roles,
        properties={
            "users": relationship(
                iam.User,
                secondary=group_role_user_associations,
                primaryjoin=f"{group_roles.name}.c.id=={group_role_user_associations.name}.c.group_role_id",
                secondaryjoin=f"{group_role_user_associations.name}.c.user_id=={users.name}.c.id",
                back_populates="group_roles",
                uselist=True,
                collection_class=set,
                innerjoin=True,
            ),
            "group": relationship(
                iam.Group,
                back_populates="group_roles",
                innerjoin=True,
                collection_class=set,
            ),
        },
        eager_defaults=True,
    )

    mapper_registry.map_imperatively(
        iam.Group,
        groups,
        properties={
            "group_roles": relationship(
                iam.GroupRoles,
                back_populates="group",
                uselist=True,
                collection_class=set,
            )
        },
        eager_defaults=True,
    )
    mapper_registry.map_imperatively(
        outbox.OutBox,
        outboxes,
        eager_defaults=True,
    )
