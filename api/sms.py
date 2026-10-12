import logging
from typing import Protocol

from phone import mask_phone
from settings import get_settings

logger = logging.getLogger("billcheck.sms")


class SmsSender(Protocol):
    def send_otp(self, phone: str, code: str) -> None: ...


class ConsoleSmsSender:
    """Development only: prints the code to the API's console instead of
    sending an SMS. Settings refuse this in production."""

    def send_otp(self, phone: str, code: str) -> None:
        logger.warning("OTP for %s is %s (console delivery, not sent by SMS)", mask_phone(phone), code)


def get_sms_sender() -> SmsSender:
    """FastAPI dependency. Add a real provider here (e.g. MSG91, Twilio)."""
    match get_settings().otp_delivery:
        case "console":
            return ConsoleSmsSender()
