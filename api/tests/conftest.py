import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# The audit is tested against the illustrative price list on purpose; outside
# the tests, sample prices raise no flag. Set before settings are first read.
os.environ.setdefault("ALLOW_SAMPLE_PRICES", "true")

import tables  # noqa: E402, F401  (registers the tables on Base.metadata)
from db import Base, get_db
from main import app
from sms import get_sms_sender

PHONE = "+919876543210"


class FakeSms:
    """Captures codes instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_otp(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))

    def last_code(self) -> str:
        return self.sent[-1][1]


@pytest.fixture
def sms() -> FakeSms:
    return FakeSms()


@pytest.fixture
def sessions() -> Iterator[sessionmaker[Session]]:
    """A fresh in-memory database per test, and the way to open one on it.

    Separate from `client` so a test can look at what an endpoint wrote: ask
    for both and they are the same database.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(sessions: sessionmaker[Session]) -> Iterator[Session]:
    """A session on the client's database, for reading back what it stored."""
    with sessions() as session:
        yield session


@pytest.fixture
def client(sms: FakeSms, sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    factory = sessions

    def get_test_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_sms_sender] = lambda: sms
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sign_up(client: TestClient, sms: FakeSms, phone: str = PHONE, name: str = "Rohan Sharma") -> dict:
    """Runs the full sign-up flow and returns the LoggedIn body."""
    assert client.post("/auth/otp/request", json={"phone": phone}).status_code == 202
    verify = client.post("/auth/otp/verify", json={"phone": phone, "code": sms.last_code()})
    assert verify.json()["status"] == "signup_required"
    response = client.post(
        "/auth/signup", json={"signup_token": verify.json()["signup_token"], "name": name, "consent": True}
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_headers(client: TestClient, sms: FakeSms) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_up(client, sms)['token']}"}
