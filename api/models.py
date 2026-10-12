from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class LineItem(BaseModel):
    """One row of an itemized hospital bill. Amounts are in rupees."""

    name: str
    detail: str | None = Field(default=None, description='Quantity or date as printed, e.g. "6 vials".')
    amount: float


class BillUploadResponse(BaseModel):
    id: str
    status: Literal["received"]
    content_type: str
    size_bytes: int
    line_items: list[LineItem] = Field(
        default_factory=list,
        description="Structured rows from the bill. Empty until OCR is wired up.",
    )
