from uuid import UUID
from app.domain import iam
from app.domain import commands
from app.service_layer.unit_of_work import AbstractUnitOfWork
from . import exceptions


class IAMService:
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
