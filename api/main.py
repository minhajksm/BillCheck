from fastapi import FastAPI

import bills
from models import HealthResponse

app = FastAPI(
    title="BillCheck API",
    description="Checks itemized hospital bills and flags charges worth asking about.",
    version="0.1.0",
)

app.include_router(bills.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse()
