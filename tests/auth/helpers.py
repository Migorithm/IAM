from app.domain import commands, iam
from tests.fakes import f


def user_factory() -> iam.User:
    name = f.name()
    email = f.email()
    cmd = commands.CreateUser(name=name, email=email)

    user: iam.User = iam.User.create(cmd)
    return user


def group_factory() -> iam.Group:
    user_id = f.uuid4()
    group_id = f.uuid4()
    cmd = commands.CreateGroup(name="Migos", user_id=user_id, group_id=group_id)

    group = iam.Group.create(cmd)
    return group
