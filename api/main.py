from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import auth
import bills
import cases
from models import HealthResponse
from settings import get_settings

app = FastAPI(
    title="BillCheck API",
    description="Checks itemized hospital bills and flags charges worth asking about.",
    version="0.1.0",
)

# The Android app doesn't need CORS. This is for the Expo web dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(bills.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse()
