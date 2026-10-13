from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    POSTGRES_DB: str
    POSTGRES_PORT: int
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str | None = "admin"
    SMTP_PASSWORD: str | None = "some_password"
    SMTP_USE_TLS: bool = False
    EMAIL_SENDER_ADDRESS: str = "noreply@example.com"

    BASE_URL: str = "http://127.0.0.1:8000"
    API_VERSION_PREFIX: str = "/api/v1"
    DOCS_REQUIRE_AUTH: bool = True
    ACTIVATION_TOKEN_LIFETIME_DAYS: int = 1
    PASSWORD_RESET_TOKEN_LIFETIME_MINUTES: int = 15
    EXPIRED_TOKEN_CLEANUP_INTERVAL_MINUTES: int = 60

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES: int = 15
    JWT_REFRESH_TOKEN_LIFETIME_DAYS: int = 7

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def POSTGRES_URL(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
