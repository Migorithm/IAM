from uuid import UUID
from app.domain import iam
from app.domain import commands
from app.service_layer.unit_of_work import AbstractUnitOfWork
from . import exceptions


def prep_cls(cls):
    for key, val in vars(cls).items():
        # add tag on class and static methods
        if getattr(val, "__func__", None):
            val.__func__.uow_required = "uow" in val.__func__.__code__.co_varnames
            setattr(cls, key, val)

        # add tag on instance methods
        elif callable(val):
            val.uow_required = "uow" in val.__code__.co_varnames
            setattr(cls, key, val)
    return cls


class ServiceMeta(type):
    def __new__(cls, *args, **kwargs):
        new_cls = super().__new__(cls, *args, **kwargs)
        return prep_cls(new_cls)


class IAMService(metaclass=ServiceMeta):
    @classmethod
    async def create_user(
        cls, msg: commands.CreateUser, *, uow: AbstractUnitOfWork
    ) -> UUID:
        async with uow:
            user = iam.User.create(msg)
            await uow.users.add(user)
            await uow.commit()
            return user.id

    @classmethod
    async def request_create_group(
        cls, msg: commands.RequestCreateGroup, *, uow: AbstractUnitOfWork
    ):
        async with uow:
            try:
                user: iam.User = await uow.users.get(msg.user_id)

            except uow.users.AggregateNotFoundError:
                raise exceptions.ObjectNotFound(
                    f"User with id:{msg.user_id} Not Found!"
                )
            user.execute(msg)
            await uow.users.add(user)
            await uow.commit()
