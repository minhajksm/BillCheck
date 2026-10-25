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
    # Whether a family must sign in before using the app. With it off, the
    # app can ask for an anonymous account instead: a real user row with no
    # phone number, so every case still belongs to somebody and nothing else
    # in the API changes. The bills then live on that one device and cannot
    # be recovered, which is why the app says so before it offers it.
    require_sign_in: bool = True
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
    # How a bill photo becomes line items. "stub" returns one fixed sample
    # bill and needs no key; "claude" reads the real pages.
    ocr_provider: Literal["stub", "claude"] = "stub"
    anthropic_api_key: str = ""
    # A family waits for every token of the answer, and the answer is thousands
    # of them, so the reading is paced by how fast the model writes. Haiku is
    # the fastest of the current models and this is transcription against an
    # explicit checklist rather than open reasoning. Set OCR_MODEL to compare:
    # the bills in tests/data are what to compare on.
    ocr_model: str = "claude-haiku-5-5"
    # How hard the reader thinks. On one real bill the thinking was 4,194 of
    # 11,377 output tokens -- over a third of the wait -- and the four phases
    # already say what to do, step by step. Raise it if findings start being
    # missed; that is the trade this setting makes.
    ocr_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    # Keeps every observation the reader makes, including the ones review.py
    # would drop: a claim the rows contradict, one the reader itself called
    # low confidence, one a price list already covers. For looking at what the
    # reader does across different bills -- it shows a family questions that
    # were checked and failed, so production refuses to start with it on.
    review_keep_all: bool = True
    # The price lists bills are checked against. The file shipped in
    # data/samples is illustrative; point this at the real NPPA and CGHS
    # lists before any flag is shown to a real family.
    reference_data_path: str = "../data/samples/reference-prices.json"
    # Whether a price marked "sample" may raise a flag. The sample list is
    # illustrative numbers made up for development: a red "above the NPPA
    # ceiling" flag computed from one tells a family their hospital broke the
    # law on the strength of a figure nobody published. Off everywhere but the
    # tests, which set it, so production raises no price flag at all until a
    # real, sourced list is loaded. Quantity norms are not affected.
    allow_sample_prices: bool = False
    # Bills one person can send to be read in 24 hours. Every read is a paid
    # Claude call, so this caps what one account can run up. A family adding
    # one bill a day per case stays far below it.
    bill_uploads_per_day: int = 20
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
            if self.ocr_provider == "stub":
                raise ValueError("OCR_PROVIDER=stub returns a sample bill instead of reading the real one.")
            if self.review_keep_all:
                raise ValueError(
                    "REVIEW_KEEP_ALL=true shows families questions the rows already contradicted."
                )
        return self

    @model_validator(mode="after")
    def check_ocr_provider(self) -> Self:
        if self.ocr_provider == "claude" and not self.anthropic_api_key:
            raise ValueError("OCR_PROVIDER=claude needs ANTHROPIC_API_KEY.")
        return self

    @model_validator(mode="after")
    def check_sms_provider(self) -> Self:
        if self.otp_delivery == "msg91" and not (self.msg91_auth_key and self.msg91_template_id):
            raise ValueError("OTP_DELIVERY=msg91 needs MSG91_AUTH_KEY and MSG91_TEMPLATE_ID.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
