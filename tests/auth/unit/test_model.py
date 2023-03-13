from uuid import UUID

import pytest
from app.domain import commands, enums, iam, exceptions
from tests.auth import helpers
from tests.fakes import f


# User Model
def test_create_user():
    name = "Migo"
    email = "whatsoever@mail.com"
    cmd = commands.CreateUser(name=name, email=email)
    user: iam.User = iam.User.create(cmd)
    assert user
    assert user.name == "Migo"
    assert user.email == email
    assert user.permissions == enums.AccessPermission.DEFAULT
    assert user.email_verified is False


def test_make_purchase():
    user = helpers.user_factory()

    cmd = commands.MakePurchase(requested_access=enums.AccessPermission.ACADEMIC)
    user.execute(cmd)
    assert len(user.events) == 3
    assert isinstance(user.events[-1], iam.User.PermissionAssigned)
    assert user.has_permission(enums.AccessPermission.ACADEMIC)


def test_create_group_request():
    user = helpers.user_factory()

    cmd = commands.RequestCreateGroup(name="SVB")
    user.execute(cmd)
    assert len(user.events) == 2
    assert isinstance(user.events[-1], iam.User.CreateGroupRequested)
    event = user.events[-1]
    assert event.name == "SVB"
    assert event.user_id == user.id
    assert isinstance(event.group_id, UUID)


def test_expire_permission():
    user = helpers.user_factory()
    cmd = commands.MakePurchase(requested_access=enums.AccessPermission.ACADEMIC)
    user.execute(cmd)

    assert len(user.events) == 3
    assert isinstance(user.events[-1], iam.User.PermissionAssigned)
    assert user.has_permission(enums.AccessPermission.ACADEMIC)

    cmd2 = commands.ExpirePermission(
        expired_permissions=[enums.AccessPermission.ACADEMIC]
    )
    user.execute(cmd2)
    assert len(user.events) == 4
    assert isinstance(user.events[-1], iam.User.PermissionExpired)
    assert not user.has_permission(enums.AccessPermission.ACADEMIC)


# Group Model
def test_create_group():
    user_id = f.uuid4()
    group_id = f.uuid4()
    cmd = commands.CreateGroup(name="Migos", user_id=user_id, group_id=group_id)

    group: iam.Group = iam.Group.create(cmd)

    assert group
    assert group.created_by == user_id
    assert group.id == group_id
    assert len(group.events) != 0
    assert len(group.events) == 1


def test_make_group_level_purchase():
    group = helpers.group_factory()
    cmd = commands.MakePurchase(
        is_group_purchase=True, requested_access=enums.AccessPermission.CHEM
    )
    group.execute(cmd)
    assert len(group.events) == 3
    assert isinstance(group.events[-1], iam.Group.PermissionAssigned)
    assert group.has_permission(enums.AccessPermission.CHEM)

    with pytest.raises(exceptions.InvalidOperation):
        cmd = commands.MakePurchase(
            is_group_purchase=False, requested_access=enums.AccessPermission.CHEM
        )
        group.execute(cmd)


def test_create_group_role():
    group = helpers.group_factory()
    cmd = commands.CreateGroupRole(
        role_name="manager", group_permissions=enums.GroupPermission.ADD_USER
    )
    group.execute(cmd)
    assert len(group.events) == 2
    assert isinstance(group.events[-1], iam.Group.GroupRoleCreated)
    role = next(r for r in group.group_roles if r.name == "manager")

    group_permissions = role.list_group_permissions()
    assert enums.GroupPermission.ADD_USER in group_permissions
    assert enums.GroupPermission.ADMIN not in group_permissions
