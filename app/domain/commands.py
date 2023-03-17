from __future__ import annotations
from uuid import UUID

from app.utils.events.meta import ImmutableObject
from app.domain import enums
from dataclasses import field


class Command(ImmutableObject):
    pass


class CreateUser(Command):
    name: str
    email: str = ""


class MakePurchase(Command):
    requested_access: list[enums.AccessPermission] = field(default_factory=list)
    is_group_purchase: bool = False

    def _refine_command(self) -> MakePurchase:
        if not isinstance(self.requested_access, list):
            return MakePurchase(
                requested_access=[self.requested_access],
                is_group_purchase=self.is_group_purchase,
            )
        return self

    def _create_chained_command(self) -> AssignPermission:
        return AssignPermission(requested_access=self.requested_access)  # type: ignore


class RequestCreateGroup(Command):
    name: str
    user_id: UUID


class CreateGroupRole(Command):
    role_name: str
    group_permissions: list[enums.GroupPermission]

    def _refine_command(self) -> CreateGroupRole:
        if not isinstance(self.group_permissions, list):
            return CreateGroupRole(
                role_name=self.role_name,
                group_permissions=[self.group_permissions],
            )
        return self


class CreateGroupLevelPurchase(Command):
    requested_access: enums.AccessPermission


class AddUser(Command):
    user_id: UUID
    group_id: UUID


class AssignGroupRole(Command):
    user_id: UUID
    group_id: UUID


class AssignPermission(Command):
    requested_access: list[enums.AccessPermission] = field(default_factory=list)

    def _refine_command(self) -> AssignPermission:
        if not isinstance(self.requested_access, list):
            return MakePurchase(
                requested_access=[self.requested_access],
            )
        return self


class DeleteUser(Command):
    ...


class ExpirePermission(Command):
    expired_permissions: list[int]


class CreateGroup(Command):
    name: str
    user_id: UUID
    group_id: UUID
