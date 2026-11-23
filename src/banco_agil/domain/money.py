from decimal import Decimal


def format_brl(value: Decimal) -> str:
    integer, _, decimals = f"{value:,.2f}".partition(".")
    return f"R$ {integer.replace(',', '.')},{decimals}"
