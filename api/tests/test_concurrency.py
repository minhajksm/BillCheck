"""Reading a bill must not hold up anyone else's request."""

import asyncio
import io
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from ocr import StubOcr, get_ocr_provider
from tests.test_cases_and_bills import JPEG, new_case


class SlowOcr:
    """Blocks inside read_bill until the test lets it go, like a slow Claude call."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def read_bill(self, pages):
        self.started.set()
        self.release.wait(timeout=10)
        return StubOcr().read_bill(pages)


@pytest.mark.anyio
async def test_other_requests_are_answered_while_a_bill_is_read(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    slow = SlowOcr()
    app.dependency_overrides[get_ocr_provider] = lambda: slow

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        upload = asyncio.create_task(
            api.post(
                f"/cases/{case['id']}/bills",
                headers=auth_headers,
                files=[("pages", ("page1.jpg", io.BytesIO(JPEG), "image/jpeg"))],
            )
        )
        try:
            # Wait until the upload is inside the reader.
            for _ in range(200):
                if slow.started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert slow.started.is_set(), "the upload never reached the reader"

            # If the reader ran on the event loop, this would wait for it.
            health = await asyncio.wait_for(api.get("/health"), timeout=2)
            assert health.status_code == 200
            assert not upload.done(), "the bill shouldn't finish until the reader is released"
        finally:
            slow.release.set()

        response = await upload
    assert response.status_code == 201, response.text


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
