import re

_CPF_IN_TEXT = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
_NON_DIGITS = re.compile(r"\D")


def is_valid_cpf(digits: str) -> bool:
    if len(digits) != 11 or not digits.isdigit() or len(set(digits)) == 1:
        return False
    for position in (9, 10):
        total = sum(int(digits[i]) * (position + 1 - i) for i in range(position))
        if (total * 10 % 11) % 10 != int(digits[position]):
            return False
    return True


def normalize_cpf(raw: str) -> str | None:
    cleaned = raw.strip()
    if not re.fullmatch(r"[\d.\-\s]+", cleaned):
        return None
    digits = _NON_DIGITS.sub("", cleaned)
    return digits if is_valid_cpf(digits) else None


def find_cpf(text: str) -> str | None:
    for match in _CPF_IN_TEXT.finditer(text):
        digits = _NON_DIGITS.sub("", match.group(1))
        if is_valid_cpf(digits):
            return digits
    return None
