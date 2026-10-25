"""A stand-in for MSG91, for testing the SMS path without sending an SMS.

Sending a real SMS through MSG91 needs a DLT-approved template, which takes
weeks to clear. This serves MSG91's Flow API at http://localhost:8091/ so the
`msg91` delivery path can be exercised end to end before then: the API builds
the real request, this answers the way MSG91 does, and the code is printed
here instead of being sent.

    uv run python scripts/fake_msg91.py            # accepts everything
    uv run python scripts/fake_msg91.py --refuse   # answers like MSG91 does
                                                   # for a bad template, so
                                                   # you can see the app's
                                                   # "couldn't send" message

Point the API at it in api/.env:

    OTP_DELIVERY=msg91
    MSG91_AUTH_KEY=fake-key
    MSG91_TEMPLATE_ID=fake-template
    MSG91_URL=http://localhost:8091/

Never for production: it sends nothing.
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8091


class Handler(BaseHTTPRequestHandler):
    refuse = False

    def do_POST(self) -> None:  # noqa: N802  (BaseHTTPRequestHandler's spelling)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except ValueError:
            self._reply(400, {"type": "error", "message": "body isn't JSON"})
            return

        if not self.headers.get("authkey"):
            self._reply(401, {"type": "error", "message": "missing authkey"})
            return

        if self.refuse:
            self._reply(200, {"type": "error", "message": "template not approved"})
            return

        for recipient in payload.get("recipients", []):
            mobile = recipient.get("mobiles", "?")
            code = recipient.get("otp", "?")
            print(f"  SMS to +{mobile}: your FairCare code is {code}", flush=True)

        self._reply(200, {"type": "success", "message": "fake-request-id"})

    def _reply(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: object) -> None:
        """Quieter than the default, which logs every request twice over."""
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refuse", action="store_true", help="refuse every message, as MSG91 would")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    Handler.refuse = args.refuse
    mode = "refusing every message" if args.refuse else "accepting messages"
    print(f"Fake MSG91 on http://localhost:{args.port}/, {mode}. Codes appear below.", flush=True)
    try:
        HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
