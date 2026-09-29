"""HMAC tokenization. Raw identifiers never reach the model or the logs."""

from __future__ import annotations

import hashlib
import hmac


def tokenize(value, secret: bytes):
    if value is None or value == "":
        return None
    digest = hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:24]
