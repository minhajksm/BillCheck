from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-only-secret-change-me"


class Settings(BaseSettings):
    """Read from environment variables, or from api/.env when running locally."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://billcheck:billcheck@localhost:5432/billcheck"
    # Signs OTP hashes. Must be a long random value outside development.
    secret_key: str = DEV_SECRET_KEY
    # "console" logs codes instead of sending SMS. Only for development.
    otp_delivery: Literal["console"] = "console"
    # Origins allowed to call the API from a browser (Expo web dev server).
    cors_origins: list[str] = ["http://localhost:8081"]

    @model_validator(mode="after")
    def check_production(self) -> Self:
        if self.environment == "production":
            if self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32:
                raise ValueError("Set SECRET_KEY to a random value of at least 32 characters in production.")
            if self.otp_delivery == "console":
                raise ValueError(
                    "OTP_DELIVERY=console would log codes instead of sending them in production."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
