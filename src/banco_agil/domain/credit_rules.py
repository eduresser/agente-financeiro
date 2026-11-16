import re
from decimal import Decimal, InvalidOperation

_NON_NUMERIC = re.compile(r"[^\d.,]")


def parse_amount(raw: str) -> Decimal | None:
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
    if not value.is_finite():
        return None
    return -value if re.search(r"-\s*(R\$)?\s*\d", raw) else value


def is_increase(current: Decimal, requested: Decimal) -> bool:
    return requested > current


def is_approved(requested: Decimal, ceiling: Decimal) -> bool:
    return requested <= ceiling


def format_brl(value: Decimal) -> str:
    integer, _, decimals = f"{value:,.2f}".partition(".")
    return f"R$ {integer.replace(',', '.')},{decimals}"
