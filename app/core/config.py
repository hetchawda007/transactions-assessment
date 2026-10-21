from functools import lru_cache
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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
        """Normalize PostgreSQL credentials and asyncpg connection options."""
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
            value = value.replace(
                "postgresql+psycopg://", "postgresql+asyncpg://", 1
            )
        elif value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

        # SQLAlchemy passes URL query parameters as keyword arguments to
        # asyncpg.connect(). Render supplies `sslmode`, while asyncpg's keyword
        # is named `ssl`; leaving it unchanged prevents application startup.
        parsed = urlsplit(value)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        ssl_mode = query.pop("sslmode", None)
        if ssl_mode is not None:
            query.setdefault("ssl", ssl_mode)

        return urlunsplit(parsed._replace(query=urlencode(query)))

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
