import logging
from functools import lru_cache

import redis
from pydantic import Field
from pydantic_settings import BaseSettings

API_V1_STR = "/api"


@lru_cache
def get_config() -> "Config":
    return Config()


log = logging.getLogger()


DB_HOST_DEFAUL = "postgres"
DB_POOL_SIZE_DEFAUL = "10"
DB_DATABASE_DEFAULT = "postgres"
DB_USER_DEFAULT = "postgres"
DB_PASSWORD_DEFAULT = "postgres"


class Config(BaseSettings):
    """Configuration with secure environment variable handling."""

    # Authentication settings
    admin_login: str = Field(default="admin", alias="ADMIN_LOGIN", description="Admin login username")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD", description="Admin password")
    jwt_secret_key: str = Field(
        default="default_secret_key_change_in_production",
        alias="JWT_SECRET_KEY",
        description="JWT signing secret",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")

    # Database settings
    db_database: str = Field(default=DB_DATABASE_DEFAULT, alias="POSTGRES_DB")
    db_user: str = Field(default=DB_USER_DEFAULT, alias="POSTGRES_USER")
    db_password: str = Field(default=DB_PASSWORD_DEFAULT, alias="POSTGRES_PASSWORD")
    db_host: str = Field(default=DB_HOST_DEFAUL, alias="POSTGRES_HOST")
    db_pool_size: int = Field(default=int(DB_POOL_SIZE_DEFAUL), alias="DB_POOL_SIZE")

    # Message queue settings
    mq_user: str = Field(default="guest", alias="AMQP_USERNAME", description="Message queue username")
    mq_password: str = Field(
        default="guest",
        alias="AMQP_PASSWORD",
        description="Message queue password",
    )
    mq_host: str = Field(default="localhost", alias="AMQP_HOST", description="Message queue host")
    mq_port: str = Field(default="6379", alias="AMQP_PORT", description="Message queue port")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        log.info(
            f"Backend started with MQ '{self.mq_uri}' and DB '{self.db_uri}', celery '{self.celery_backend_uri}', '{self.celery_broker_uri}'",
        )

    @property
    def db_uri(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}@"
            f"{self.db_host}/{self.db_database}"
        )

    @property
    def mq_uri(self) -> str:
        return f"pyamqp://{self.mq_user}:{self.mq_password}@{self.mq_host}:{self.mq_port}/"

    @property
    def redis_host(self) -> str:
        return self.mq_host

    @property
    def redis_port(self) -> int:
        return int(self.mq_port)

    @property
    def redis_db(self) -> int:
        return 1

    @property
    def redis(self) -> redis.Redis:  # type: ignore
        return redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            db=self.redis_db,
        )

    @property
    def redis_password(self) -> str:
        return self.mq_password

    @property
    def celery_broker_uri(self) -> str:
        return f"redis://:{self.mq_password}@{self.mq_host}:{self.mq_port}/0"

    @property
    def celery_backend_uri(self) -> str:
        return self.celery_broker_uri
