import logging
from functools import lru_cache
from typing import Protocol

import httpx

from phone import mask_phone
from settings import get_settings

logger = logging.getLogger("billcheck.sms")


class SmsDeliveryError(Exception):
    """The provider refused the message or couldn't be reached. Callers turn
    this into an error the app can show, and drop the OTP challenge so the
    user isn't held back by the resend cooldown."""


class SmsSender(Protocol):
    def send_otp(self, phone: str, code: str) -> None: ...


class ConsoleSmsSender:
    """Development only: prints the code to the API's console instead of
    sending an SMS. Settings refuse this in production."""

    def send_otp(self, phone: str, code: str) -> None:
        logger.warning("OTP for %s is %s (console delivery, not sent by SMS)", mask_phone(phone), code)


class Msg91SmsSender:
    """Sends the code by SMS through MSG91, an Indian SMS aggregator.

    The message text isn't here. It lives in a DLT-approved template in the
    MSG91 dashboard, because TRAI rules require every transactional SMS to
    match a registered template. We send the template id and the code as a
    template variable, and MSG91 fills it in.

    The template's variable must be named `otp`, or change VARIABLE to match
    it. MSG91 variable names are case-sensitive.

    Never logs the code: unlike console delivery, this is used in production.
    """

    VARIABLE = "otp"
    TIMEOUT = 10.0

    def __init__(
        self,
        auth_key: str,
        template_id: str,
        sender_id: str = "",
        url: str = "https://control.msg91.com/api/v5/flow/",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._template_id = template_id
        self._sender_id = sender_id
        self._client = httpx.Client(
            headers={"authkey": auth_key, "accept": "application/json"},
            timeout=self.TIMEOUT,
            transport=transport,
        )

    def send_otp(self, phone: str, code: str) -> None:
        # MSG91 wants the country code without the "+": "919876543210".
        payload: dict[str, object] = {
            "template_id": self._template_id,
            "short_url": 0,
            "recipients": [{"mobiles": phone.removeprefix("+"), self.VARIABLE: code}],
        }
        if self._sender_id:
            payload["sender"] = self._sender_id

        try:
            response = self._client.post(self._url, json=payload)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise SmsDeliveryError(f"MSG91 request failed: {exc}") from exc
        except ValueError as exc:
            raise SmsDeliveryError("MSG91 returned a body that isn't JSON.") from exc

        # MSG91 answers 200 even for some refusals, so the body decides.
        if str(body.get("type", "")).lower() != "success":
            raise SmsDeliveryError(f"MSG91 refused the message: {body}")

        logger.info("OTP sent to %s via MSG91 (request %s)", mask_phone(phone), body.get("message"))


@lru_cache
def get_sms_sender() -> SmsSender:
    """FastAPI dependency. One sender per process, so MSG91 requests reuse
    the same HTTP connection pool."""
    settings = get_settings()
    match settings.otp_delivery:
        case "console":
            return ConsoleSmsSender()
        case "msg91":
            return Msg91SmsSender(
                auth_key=settings.msg91_auth_key,
                template_id=settings.msg91_template_id,
                sender_id=settings.msg91_sender_id,
                url=settings.msg91_url,
            )
