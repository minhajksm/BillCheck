"""Phone number + OTP sign-in.

1. POST /auth/otp/request sends a 6-digit code to the number.
2. POST /auth/otp/verify checks it. Existing users get a session token.
   New numbers get a short-lived signup token instead.
3. POST /auth/signup takes that token, a name, and DPDP consent, and creates
   the account.

The app sends the session token as `Authorization: Bearer <token>`.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_db, utcnow
from models import (
    ApiError,
    LoggedIn,
    OtpRequest,
    OtpRequestResponse,
    OtpVerify,
    OtpVerifyResponse,
    Signup,
    SignupRequired,
    UserOut,
)
from phone import mask_phone
from settings import get_settings
from sms import SmsDeliveryError, SmsSender, get_sms_sender
from tables import AuthSession, OtpChallenge, User

logger = logging.getLogger("billcheck.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

OTP_TTL = timedelta(minutes=5)
RESEND_COOLDOWN = timedelta(seconds=30)
MAX_CODES_PER_HOUR = 5
MAX_ATTEMPTS = 5
SIGNUP_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=30)
# Bump when the consent text in the app changes, so we know who agreed to what.
CONSENT_VERSION = "2026-10"

Db = Annotated[Session, Depends(get_db)]

ERRORS = {
    "otp_cooldown": "Wait a moment before asking for another code.",
    "otp_rate_limited": "Too many codes requested. Try again in an hour.",
    "otp_expired": "This code has expired. Ask for a new one.",
    "otp_invalid": "That code isn't right.",
    "otp_locked": "Too many wrong tries. Ask for a new code.",
    "signup_token_invalid": "Sign-up took too long. Start again with your phone number.",
    "account_exists": "This number already has an account. Log in instead.",
    "not_authenticated": "Log in to continue.",
    "sms_failed": "Couldn't send the code just now. Try again in a moment.",
}

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    code: {"model": ApiError} for code in (400, 401, 409, 429, 502)
}


def api_error(status_code: int, code: str, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]}, headers=headers)


def _hash_code(phone: str, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_session(db: Session, user: User) -> LoggedIn:
    token = secrets.token_urlsafe(32)
    session = AuthSession(user_id=user.id, token_hash=_hash_token(token), expires_at=utcnow() + SESSION_TTL)
    db.add(session)
    db.commit()
    return LoggedIn(
        token=token, expires_at=session.expires_at, user=UserOut.model_validate(user, from_attributes=True)
    )


@router.post(
    "/otp/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OtpRequestResponse,
    responses=ERROR_RESPONSES,
)
def request_otp(
    body: OtpRequest, db: Db, sms: Annotated[SmsSender, Depends(get_sms_sender)]
) -> OtpRequestResponse:
    """Sends a code. Responds the same whether or not the number has an account."""
    now = utcnow()
    latest = db.scalar(
        select(OtpChallenge.created_at)
        .where(OtpChallenge.phone == body.phone)
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    )
    if latest and now - latest < RESEND_COOLDOWN:
        wait = int((RESEND_COOLDOWN - (now - latest)).total_seconds()) + 1
        raise api_error(status.HTTP_429_TOO_MANY_REQUESTS, "otp_cooldown", {"Retry-After": str(wait)})

    sent_last_hour = db.scalar(
        select(func.count())
        .select_from(OtpChallenge)
        .where(OtpChallenge.phone == body.phone, OtpChallenge.created_at > now - timedelta(hours=1))
    )
    if (sent_last_hour or 0) >= MAX_CODES_PER_HOUR:
        raise api_error(status.HTTP_429_TOO_MANY_REQUESTS, "otp_rate_limited", {"Retry-After": "3600"})

    code = f"{secrets.randbelow(10**6):06d}"
    challenge = OtpChallenge(
        phone=body.phone,
        code_hash=_hash_code(body.phone, code),
        created_at=now,
        expires_at=now + OTP_TTL,
    )
    db.add(challenge)
    db.commit()

    try:
        sms.send_otp(body.phone, code)
    except SmsDeliveryError:
        # Drop the challenge, so the resend cooldown and the hourly cap don't
        # hold the user back for a failure that was ours.
        logger.exception("Couldn't send an OTP to %s", mask_phone(body.phone))
        db.delete(challenge)
        db.commit()
        raise api_error(status.HTTP_502_BAD_GATEWAY, "sms_failed") from None

    return OtpRequestResponse(
        expires_in_seconds=int(OTP_TTL.total_seconds()),
        resend_after_seconds=int(RESEND_COOLDOWN.total_seconds()),
    )


@router.post("/otp/verify", response_model=OtpVerifyResponse, responses=ERROR_RESPONSES)
def verify_otp(body: OtpVerify, db: Db) -> LoggedIn | SignupRequired:
    """Checks the latest code sent to the number. Only that code counts."""
    now = utcnow()
    challenge = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == body.phone)
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    )
    if challenge is None or challenge.verified_at is not None or challenge.expires_at <= now:
        raise api_error(status.HTTP_400_BAD_REQUEST, "otp_expired")
    if challenge.attempts >= MAX_ATTEMPTS:
        raise api_error(status.HTTP_400_BAD_REQUEST, "otp_locked")

    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _hash_code(body.phone, body.code)):
        db.commit()
        locked = challenge.attempts >= MAX_ATTEMPTS
        raise api_error(status.HTTP_400_BAD_REQUEST, "otp_locked" if locked else "otp_invalid")

    challenge.verified_at = now
    user = db.scalar(select(User).where(User.phone == body.phone))
    if user is not None:
        return _new_session(db, user)

    signup_token = secrets.token_urlsafe(32)
    challenge.signup_token_hash = _hash_token(signup_token)
    challenge.signup_expires_at = now + SIGNUP_TTL
    db.commit()
    return SignupRequired(signup_token=signup_token, expires_at=challenge.signup_expires_at)


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=LoggedIn, responses=ERROR_RESPONSES
)
def signup(body: Signup, db: Db) -> LoggedIn:
    now = utcnow()
    challenge = db.scalar(
        select(OtpChallenge).where(OtpChallenge.signup_token_hash == _hash_token(body.signup_token))
    )
    if (
        challenge is None
        or challenge.signup_used_at is not None
        or challenge.signup_expires_at is None
        or challenge.signup_expires_at <= now
    ):
        raise api_error(status.HTTP_400_BAD_REQUEST, "signup_token_invalid")

    user = User(phone=challenge.phone, name=body.name, consent_version=CONSENT_VERSION, consented_at=now)
    challenge.signup_used_at = now
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise api_error(status.HTTP_409_CONFLICT, "account_exists") from None
    return _new_session(db, user)


_bearer = HTTPBearer(auto_error=False)


def _current_session(
    db: Db, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> AuthSession:
    unauthorized = api_error(
        status.HTTP_401_UNAUTHORIZED, "not_authenticated", {"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(credentials.credentials))
    )
    if session is None or session.revoked_at is not None or session.expires_at <= utcnow():
        raise unauthorized
    return session


CurrentSession = Annotated[AuthSession, Depends(_current_session)]


def current_user(db: Db, session: CurrentSession) -> User:
    """FastAPI dependency for endpoints that need a signed-in user."""
    user = db.get(User, session.user_id)
    if user is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


@router.get("/me", response_model=UserOut, responses=ERROR_RESPONSES)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES)
def logout(db: Db, session: CurrentSession) -> Response:
    session.revoked_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
