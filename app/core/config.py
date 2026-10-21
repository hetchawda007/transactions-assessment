from functools import lru_cache
from urllib.parse import quote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Transactions API"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/transactions"
    )
    external_api_url: str = "https://jsonplaceholder.typicode.com/posts"
    external_request_timeout_seconds: float = 5.0

    @field_validator("database_url", mode="after")
    @classmethod
    def use_asyncpg_driver(cls, value: str) -> str:
        """Normalize PostgreSQL credentials and select the asyncpg driver."""
        if "://" in value:
            scheme, remainder = value.split("://", 1)
            if "@" in remainder:
                credentials, location = remainder.rsplit("@", 1)
                if ":" in credentials:
                    username, password = credentials.split(":", 1)
                    credentials = (
                        f"{quote(username, safe='%')}:{quote(password, safe='%')}"
                    )
                    value = f"{scheme}://{credentials}@{location}"

        if value.startswith("postgresql+psycopg://"):
            return value.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRANSACTIONS_",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
