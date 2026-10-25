"""Health, and what the bill upload accepts as a page.

The upload's job before OCR is to decide whether this is a photograph at all.
It reads the file's own bytes rather than the client's Content-Type header,
which anything can set.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import bills
from db import india_today

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64


@pytest.fixture
def case_id(client: TestClient, auth_headers: dict[str, str]) -> str:
    member = client.post("/members", json={"name": "Papa"}, headers=auth_headers).json()
    response = client.post(
        "/cases",
        json={
            "member_id": member["id"],
            "title": "Papa's admission",
            "hospital_name": "City Care Hospital",
            "hospital_area": "Andheri",
            "patient_name": "Ramesh Sharma",
            "ip_number": "20841",
            "admitted_on": str(india_today() - timedelta(days=2)),
        },
        headers=auth_headers,
    )
    return response.json()["id"]


def upload(
    client: TestClient,
    headers: dict[str, str],
    case_id: str,
    content: bytes,
    content_type: str = "image/jpeg",
):
    return client.post(
        f"/cases/{case_id}/bills",
        headers=headers,
        files=[("pages", ("bill.jpg", content, content_type))],
    )


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    # The app reads `anonymous_accounts` here to decide whether to offer
    # "use it without signing in", so it is part of the contract.
    assert response.json() == {"status": "ok", "anonymous_accounts": False}


@pytest.mark.parametrize(
    ("content", "label"),
    [(JPEG, "jpeg"), (PNG, "png"), (WEBP, "webp"), (HEIC, "heic")],
)
def test_upload_accepts_photo_formats(
    client: TestClient, auth_headers: dict[str, str], case_id: str, content: bytes, label: str
):
    response = upload(client, auth_headers, case_id, content)
    assert response.status_code == 201, f"{label} should be accepted as a bill page"
    assert response.json()["page_count"] == 1


def test_upload_requires_sign_in(client: TestClient, case_id: str):
    response = upload(client, {}, case_id, JPEG)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"


def test_upload_trusts_file_bytes_over_header(client: TestClient, auth_headers: dict[str, str], case_id: str):
    """A spreadsheet announced as a JPEG is still a spreadsheet."""
    response = upload(client, auth_headers, case_id, b"PK\x03\x04" + b"\x00" * 64)
    assert response.status_code == 415


def test_upload_accepts_a_pdf(client: TestClient, auth_headers: dict[str, str], case_id: str):
    """Families are often handed the bill as a PDF rather than on paper."""
    response = upload(client, auth_headers, case_id, b"%PDF-1.7\n" + b"\x00" * 64, "application/pdf")
    assert response.status_code == 201, response.text


def test_upload_rejects_an_empty_page(client: TestClient, auth_headers: dict[str, str], case_id: str):
    assert upload(client, auth_headers, case_id, b"").status_code == 400


def test_upload_rejects_an_oversized_page(
    client: TestClient, auth_headers: dict[str, str], case_id: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(bills, "MAX_UPLOAD_BYTES", 1024)
    assert upload(client, auth_headers, case_id, JPEG + b"\x00" * 2048).status_code == 413


def test_upload_requires_at_least_one_page(client: TestClient, auth_headers: dict[str, str], case_id: str):
    assert client.post(f"/cases/{case_id}/bills", headers=auth_headers).status_code == 422


def test_upload_rejects_too_many_pages(
    client: TestClient, auth_headers: dict[str, str], case_id: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(bills, "MAX_PAGES", 2)
    response = client.post(
        f"/cases/{case_id}/bills",
        headers=auth_headers,
        files=[("pages", (f"p{i}.jpg", JPEG, "image/jpeg")) for i in range(3)],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "too_many_pages"


# --- what the browser is allowed to ask for ----------------------------------


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_the_browser_may_use_every_method_the_api_answers(client: TestClient, method: str):
    """The app runs in a browser, which asks permission before a PATCH or a
    DELETE and never sends the request if the answer is no.

    These tests call endpoints directly and never ask, so a method missing from
    CORS passes everything here and is unreachable from the app. That is how
    DELETE /cases/{id} shipped: 13 passing tests, and a 400 on the preflight the
    moment a family tried it.
    """
    response = client.options(
        "/cases/bb1b4a8c-0000-0000-0000-000000000000",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200, f"the browser cannot send a {method}: {response.text}"
    assert method in response.headers.get("access-control-allow-methods", "")


def test_a_bill_that_cannot_be_read_says_why_in_the_log(
    client: TestClient, auth_headers: dict[str, str], case_id: str, monkeypatch: pytest.MonkeyPatch, caplog
):
    """The family is told one thing, because there is nothing else they can do
    about it. Whoever runs this needs the reason: a refusal, a truncated answer
    and a dead key all answer 422 unreadable_bill, and without this line they
    are indistinguishable from outside.
    """
    import ocr

    def explode(_pages):
        raise ocr.OcrError("No itemized rows were found on these pages.")

    monkeypatch.setattr(ocr.StubOcr, "read_bill", staticmethod(explode))

    with caplog.at_level("WARNING", logger="billcheck.bills"):
        response = upload(client, auth_headers, case_id, JPEG)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unreadable_bill"
    assert "No itemized rows were found" in caplog.text
    assert case_id in caplog.text
