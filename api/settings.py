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
    # How OTP codes reach the user. "console" logs them instead of sending
    # SMS and is development only; "msg91" sends a real SMS.
    otp_delivery: Literal["console", "msg91"] = "console"
    # MSG91, the SMS provider. Needed when OTP_DELIVERY=msg91.
    msg91_auth_key: str = ""
    # A DLT-approved template registered in the MSG91 dashboard. Its variable
    # must be named `otp`.
    msg91_template_id: str = ""
    # Registered sender id, e.g. "BILCHK". Blank uses the template's own.
    msg91_sender_id: str = ""
    # Where MSG91 lives. Override it only to point at scripts/fake_msg91.py,
    # which exercises this path in development without sending an SMS.
    msg91_url: str = "https://control.msg91.com/api/v5/flow/"
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

    @model_validator(mode="after")
    def check_sms_provider(self) -> Self:
        if self.otp_delivery == "msg91" and not (self.msg91_auth_key and self.msg91_template_id):
            raise ValueError("OTP_DELIVERY=msg91 needs MSG91_AUTH_KEY and MSG91_TEMPLATE_ID.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
