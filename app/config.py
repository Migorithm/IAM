from pydantic import BaseSettings
import typing
from os import getenv


STAGE = typing.cast(
    typing.Literal[
        "local", "ci-testing", "testing", "develop", "staging", "production"
    ],
    getenv("STAGE", "local"),
)


class DbSettings(BaseSettings):
    db_protocol: str = "postgresql+asyncpg"
    db_user: str = "duperuser"
    db_password: str = "abc123"
    db_host: str = "localhost"
    db_port: str = "5432"
    db_name: str = "iam_service"

    class Config:
        env_file = "../.env"

    def get_uri(self):
        return "{}://{}:{}@{}:{}/{}".format(
            self.db_protocol,
            self.db_user,
            self.db_password,
            self.db_host,
            self.db_port,
            self.db_name,
        )


db_settings = DbSettings()
