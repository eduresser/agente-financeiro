import re
from decimal import Decimal, InvalidOperation

_NON_NUMERIC = re.compile(r"[^\d.,]")


_MAGNITUDE = re.compile(r"(\d[\d.,]*)\s*(mil|k|milh[ãa]o|milh[õo]es)\b", re.IGNORECASE)
_MULTIPLIER = {"mil": 1_000, "k": 1_000}


def _to_decimal(raw: str) -> Decimal | None:
    cleaned = _NON_NUMERIC.sub("", raw.replace("R$", ""))
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_amount(raw: str) -> Decimal | None:
    magnitude = _MAGNITUDE.search(raw)
    if magnitude:
        base = _to_decimal(magnitude.group(1))
        unit = magnitude.group(2).lower()
        value = None if base is None else base * _MULTIPLIER.get(unit, 1_000_000)
    else:
        value = _to_decimal(raw)
    if value is None:
        return None
    return -value if re.search(r"-\s*(R\$)?\s*\d", raw) else value


def is_approved(requested: Decimal, ceiling: Decimal) -> bool:
    return requested <= ceiling


def format_brl(value: Decimal) -> str:
    integer, _, decimals = f"{value:,.2f}".partition(".")
    return f"R$ {integer.replace(',', '.')},{decimals}"
