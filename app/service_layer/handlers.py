from app.domain import iam
from app.domain import commands
from app.service_layer.unit_of_work import AbstractUnitOfWork


class IAMService:
    @classmethod
    async def create_user(cls, msg: commands.CreateUser, *, uow: AbstractUnitOfWork):
        async with uow:
            user = iam.User.create(msg)
            await uow.users.add(user)
            await uow.commit()
