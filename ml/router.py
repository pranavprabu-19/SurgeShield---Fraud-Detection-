"""Name the champion a raw row belongs to. This does not score the row."""

from __future__ import annotations

# First match wins. More specific column sets come before broad ones.
SIGNATURES = (
    ("creditcard", ("V1", "V28"), "card PCA features"),
    ("paysim", ("nameOrig", "nameDest", "type"), "mobile money"),
    ("ieee_cis", ("ProductCD",), "e-commerce product code"),
    ("sparkov", ("cc_num", "merchant"), "card number and merchant"),
    ("nubank_baf", ("intended_amount", "customer_id"), "account-opening amount"),
    ("upi_india", ("sender_vpa", "receiver_vpa"), "UPI addresses"),
    ("ecommerce_fraud", ("purchase_time", "device_id"), "purchase time and device"),
)


def route(transaction: dict) -> tuple[str, str]:
    """Return (dataset name, why it matched). Unknown rows stay on creditcard."""
    keys = set(transaction or {})
    for name, required, label in SIGNATURES:
        if set(required).issubset(keys):
            return name, label
    return "creditcard", "default fallback"
