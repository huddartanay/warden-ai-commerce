"""Money boundary conversions. Rupees Decimal <-> paise int."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def rupees_to_paise(amount: Decimal | int | str) -> int:
    """
    Convert a rupee amount to the smallest currency unit (paise) that Razorpay's
    API expects. Rounds half-up at two decimal places.
    """
    d = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    quantized = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized * 100)


def paise_to_rupees(paise: int) -> Decimal:
    return (Decimal(int(paise)) / Decimal(100)).quantize(Decimal("0.01"))
