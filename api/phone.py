import re

_SEPARATORS = re.compile(r"[\s\-().]")
_INDIAN_MOBILE = re.compile(r"[6-9]\d{9}")


def normalize_indian_mobile(raw: str) -> str | None:
    """Returns an Indian mobile number in E.164 form ("+919876543210"), or
    None if it isn't one. Accepts the usual ways people type it:
    "98765 43210", "+91 98765-43210", "09876543210", "919876543210"."""
    digits = _SEPARATORS.sub("", raw)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if _INDIAN_MOBILE.fullmatch(digits) else None


def mask_phone(phone: str) -> str:
    """Hides most of the number for logs: +919876543210 becomes +91******3210."""
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
