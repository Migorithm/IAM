from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from functools import singledispatchmethod
from app.domain import commands
from app.utils.models import aggregate_root
from . import exceptions


from . import enums


class PermissionControl:
    permissions: int

    def add_permission(self, *perm):
        self._add_permission(*perm)

    def remove_permission(self, *perm):
        self._remove_permission(*perm)

    def has_permission(self, *perm) -> bool:
        return self._has_permission(*perm)

    def _propagate_permissions(self):
        """
        propgation logic to spread out list of permissions
        """

        pass

    def _add_permission(self, *perm):
        """
        Template method which may or may not include propagation logic
        """
        for p in perm:
            if not self.has_permission(p):
                self.permissions += p

        # propagation hook
        self._propagate_permissions()

    def _remove_permission(self, *perm):
        for p in perm:
            if self.has_permission(p):
                self.permissions -= p

    def list_permissions(self):
        return {p.value for p in enums.AccessPermission if self.has_permission(p)}

    def _has_permission(self, *perm):
        for p in perm:
            if not (self.permissions & p == p):
                return False
        return True


# TODO who imparts the permission? System? OR Group Owner? - probably both.
#! System may be triggered when billing is made
#! Admins(Not exactly system) may be able to add permission to given user


@dataclass(eq=False)
class User(aggregate_root.Aggregate, PermissionControl):
    id: UUID
    name: str

    email_verified: bool = field(default=False, compare=False)
    permissions: int = field(default=enums.AccessPermission.DEFAULT, compare=False)
    groups: set[UUID] = field(default_factory=set)
    email: str = ""
    created_at: datetime = field(init=False)
    updated_at: datetime = field(init=False)

    def __eq__(self, other: object):
        if not isinstance(other, User):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash((self.id))

    @classmethod
    def create(cls, msg: commands.CreateUser):
        """
        Create User
        """
        # TODO password hashing logic

        return super()._create_(cls.Created, name=msg.name, email=msg.email)

    @singledispatchmethod
    def execute(self, msg):
        """
        method for executing commands
        """

    @execute.register
    def make_purchase(self, msg: commands.MakePurchase):
        msg = msg._refine_command()
        # TODO There must be so many conditions and invariants
        self._trigger_(self.PurchaseMade, requested_access=msg.requested_access)
        if not msg.is_group_purchase:
            self.execute(msg._create_chained_command())

    @execute.register
    def assign_permission(self, msg: commands.AssignPermission):
        msg = msg._refine_command()
        self._trigger_(self.PermissionAssigned, requested_access=msg.requested_access)

    @execute.register
    def create_group(self, msg: commands.RequestCreateGroup):
        self._trigger_(
            self.CreateGroupRequested, name=msg.name, user_id=self.id, group_id=uuid4()
        )

    @execute.register
    def expire_permission(self, msg: commands.ExpirePermission):
        self._trigger_(
            self.PermissionExpired, expired_permissions=msg.expired_permissions
        )

    class Created(aggregate_root.Aggregate.Created):
        name: str
        email: str
        permissions: int = enums.AccessPermission.DEFAULT

    class PurchaseMade(aggregate_root.Aggregate.Event):
        requested_access: list[enums.AccessPermission]

    class PermissionAssigned(aggregate_root.Aggregate.Event):
        requested_access: list[enums.AccessPermission]

        def apply(self, user: User) -> None:
            if not user.has_permission(*self.requested_access):
                user.add_permission(*self.requested_access)

    class PermissionExpired(aggregate_root.Aggregate.Event):
        expired_permissions: list[int]

        def apply(self, user: User) -> None:
            user.remove_permission(*self.expired_permissions)

    #! Policy required
    class CreateGroupRequested(aggregate_root.Aggregate.Event):
        # ? Group shouldn't not be created at this point because
        # it belongs to a different aggregate
        # * Then How to map users to groups? Only through reference? - Yes
        name: str
        user_id: UUID
        group_id: UUID
        internally_notifiable: bool = True


@dataclass(eq=False)
class GroupRoles(PermissionControl):
    id: UUID
    name: str
    group_id: UUID
    permissions: int = field(default=enums.AccessPermission.DEFAULT, compare=False)
    group_permissions: int = field(
        default=enums.AccessPermission.DEFAULT, compare=False
    )

    users: set[User] = field(default_factory=set)
    group: Group = field(init=False)

    def __eq__(self, other: object):
        if not isinstance(other, GroupRoles):
            return False
        return self.group_id == other.group_id and self.name == other.name

    def __hash__(self):
        return hash((self.group_id, self.name))

    def has_group_permission(self, *perm):
        for p in perm:
            if not (self.group_permissions & p == p):
                return False
        return True

    def list_group_permissions(self):
        return {p.value for p in enums.AccessPermission if self.has_group_permission(p)}


@dataclass(eq=False)
class Group(aggregate_root.Aggregate, PermissionControl):
    id: UUID  # PK
    created_by: UUID
    name: str
    permissions: int = field(
        default=enums.AccessPermission.DEFAULT
    )  # Must be set by ADMIN or system
    group_permissions: int = field(default=enums.GroupPermission.DEFAULT)
    group_roles: set[GroupRoles] = field(default_factory=set)
    created_at: datetime = field(init=False)
    updated_at: datetime = field(init=False)

    def __post_init__(self):
        super().__post_init__()
        self.group_roles.add(
            GroupRoles(
                id=uuid4(),
                name="default",
                group_id=self.id,
            )
        )
        self.group_roles.add(GroupRoles(id=uuid4(), name="owner", group_id=self.id))

    @classmethod
    def create(cls, msg: commands.CreateGroup):
        """
        Create Group
        """

        return super()._create_(
            cls.Created, name=msg.name, created_by=msg.user_id, id=msg.group_id
        )

    @singledispatchmethod
    def execute(self, msg):
        """
        method for executing commands
        """

    @execute.register
    def make_purchase(self, msg: commands.MakePurchase):
        if not msg.is_group_purchase:
            raise exceptions.InvalidOperation

        msg = msg._refine_command()
        self._trigger_(self.PurchaseMade, requested_access=msg.requested_access)
        self.execute(msg._create_chained_command())

    @execute.register
    def assign_permission(self, msg: commands.AssignPermission):
        msg = msg._refine_command()
        self._trigger_(self.PermissionAssigned, requested_access=msg.requested_access)

    @execute.register
    def create_group_role(self, msg: commands.CreateGroupRole):
        msg = msg._refine_command()
        self._trigger_(
            self.GroupRoleCreated,
            role_name=msg.role_name,
            group_permissions=msg.group_permissions,
            group_id=self.id,
        )

    class Created(aggregate_root.Aggregate.Created):
        name: str
        created_by: UUID
        id: UUID

    class PurchaseMade(aggregate_root.Aggregate.Event):
        requested_access: list[enums.AccessPermission]

    #! Policy required
    class PermissionAssigned(aggregate_root.Aggregate.Event):
        requested_access: list[enums.AccessPermission]

        def apply(self, group: Group) -> None:
            if not group.has_permission(*self.requested_access):
                group.add_permission(*self.requested_access)

    class GroupRoleCreated(aggregate_root.Aggregate.Event):
        role_name: str
        group_permissions: list[enums.GroupPermission]
        group_id: UUID

        def apply(self, group: Group) -> None:
            is_existing = next(
                (r for r in group.group_roles if r.name == self.role_name), None
            )
            if not is_existing:
                group.group_roles.add(
                    GroupRoles(
                        id=uuid4(),
                        name=self.role_name,
                        group_permissions=sum(self.group_permissions),
                        group_id=self.group_id,
                    )
                )
