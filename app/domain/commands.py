from __future__ import annotations
from uuid import UUID

from app.utils.events.meta import ImmutableObject
from app.domain import enums
from dataclasses import field


class CreateUser(ImmutableObject):
    name: str
    email: str = ""


class MakePurchase(ImmutableObject):
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


class RequestCreateGroup(ImmutableObject):
    name: str


class CreateGroupRole(ImmutableObject):
    role_name: str
    group_permissions: list[enums.GroupPermission]

    def _refine_command(self) -> CreateGroupRole:
        if not isinstance(self.group_permissions, list):
            return CreateGroupRole(
                role_name=self.role_name,
                group_permissions=[self.group_permissions],
            )
        return self


class CreateGroupLevelPurchase(ImmutableObject):
    requested_access: enums.AccessPermission


class AddUser(ImmutableObject):
    user_id: UUID
    group_id: UUID


class AssignGroupRole(ImmutableObject):
    user_id: UUID
    group_id: UUID


class AssignPermission(ImmutableObject):
    requested_access: list[enums.AccessPermission] = field(default_factory=list)

    def _refine_command(self) -> AssignPermission:
        if not isinstance(self.requested_access, list):
            return MakePurchase(
                requested_access=[self.requested_access],
            )
        return self


class DeleteUser(ImmutableObject):
    ...


class ExpirePermission(ImmutableObject):
    expired_permissions: list[int]


class CreateGroup(ImmutableObject):
    name: str
    user_id: UUID
    group_id: UUID
