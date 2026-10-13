"""Health, and what the bill upload accepts as a page.

The upload's job before OCR is to decide whether this is a photograph at all.
It reads the file's own bytes rather than the client's Content-Type header,
which anything can set.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import bills

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64


@pytest.fixture
def case_id(client: TestClient, auth_headers: dict[str, str]) -> str:
    response = client.post(
        "/cases",
        json={
            "title": "Papa's admission",
            "hospital_name": "City Care Hospital",
            "hospital_area": "Andheri",
            "patient_name": "Ramesh Sharma",
            "ip_number": "20841",
            "admitted_on": str(date.today() - timedelta(days=2)),
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
    assert response.json() == {"status": "ok"}


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
    """A PDF announced as a JPEG is still a PDF."""
    response = upload(client, auth_headers, case_id, b"%PDF-1.7\n" + b"\x00" * 64)
    assert response.status_code == 415


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
