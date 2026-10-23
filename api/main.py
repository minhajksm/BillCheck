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
    # Every method the API answers. One missing is invisible from the tests,
    # which call endpoints directly, and fatal in the browser, which asks
    # permission first: the app never gets to send the request at all.
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(bills.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    # The app reads `anonymous_accounts` to decide whether to offer "use it
    # without signing in". Asking rather than carrying its own copy of the
    # setting is what keeps the button from appearing on a server that would
    # refuse it.
    return HealthResponse(anonymous_accounts=not get_settings().require_sign_in)
