from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from models import BillUploadResponse

router = APIRouter(prefix="/bills", tags=["bills"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024

HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}


def sniff_image_type(head: bytes) -> str | None:
    """Detects the image type from its first bytes, since the client's
    Content-Type header can't be trusted."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "image/heic"
    return None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BillUploadResponse)
async def upload_bill(file: UploadFile = File(description="A photo of one bill page.")) -> BillUploadResponse:
    """Accepts one bill photo. Stub: checks the upload and returns no line
    items yet. The image is read in memory and discarded, never stored."""
    size = 0
    head = b""
    while chunk := await file.read(CHUNK_BYTES):
        if not head:
            head = chunk[:16]
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Bill photos can be up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )

    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")

    content_type = sniff_image_type(head)
    if content_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a JPEG, PNG, WebP, or HEIC photo of the bill.",
        )

    return BillUploadResponse(
        id=str(uuid4()),
        status="received",
        content_type=content_type,
        size_bytes=size,
    )
