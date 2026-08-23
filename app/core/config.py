from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "fastapi-production-starter"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 5

    # Redis
    redis_url: RedisDsn

    # Auth / JWT
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Rate limiting
    rate_limit_auth_requests: int = 5
    rate_limit_auth_window_seconds: int = 60

    # Observability
    log_level: str = "INFO"
    log_json: bool = True

    # CORS
    cors_allow_origins: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
