import pytest
from fastapi.testclient import TestClient

import bills

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64


def upload(
    client: TestClient,
    headers: dict[str, str],
    content: bytes,
    content_type: str = "image/jpeg",
):
    return client.post("/bills", headers=headers, files={"file": ("bill.jpg", content, content_type)})


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("content", "expected"),
    [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"), (HEIC, "image/heic")],
)
def test_upload_accepts_images(
    client: TestClient, auth_headers: dict[str, str], content: bytes, expected: str
):
    response = upload(client, auth_headers, content)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "received"
    assert body["content_type"] == expected
    assert body["size_bytes"] == len(content)
    assert body["line_items"] == []
    assert body["id"]


def test_upload_requires_sign_in(client: TestClient):
    response = upload(client, {}, JPEG)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"


def test_upload_trusts_file_bytes_over_header(client: TestClient, auth_headers: dict[str, str]):
    response = upload(client, auth_headers, b"%PDF-1.7\n" + b"\x00" * 64, content_type="image/jpeg")
    assert response.status_code == 415


def test_upload_rejects_empty_file(client: TestClient, auth_headers: dict[str, str]):
    assert upload(client, auth_headers, b"").status_code == 400


def test_upload_rejects_large_file(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(bills, "MAX_UPLOAD_BYTES", 1024)
    assert upload(client, auth_headers, JPEG + b"\x00" * 2048).status_code == 413


def test_upload_requires_file(client: TestClient, auth_headers: dict[str, str]):
    assert client.post("/bills", headers=auth_headers).status_code == 422
