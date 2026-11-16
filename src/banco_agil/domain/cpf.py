import re

_CPF_IN_TEXT = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
_NON_DIGITS = re.compile(r"\D")


def normalize_cpf(raw: str) -> str | None:
    cleaned = raw.strip()
    if not re.fullmatch(r"[\d.\-\s]+", cleaned):
        return None
    digits = _NON_DIGITS.sub("", cleaned)
    return digits if len(digits) == 11 else None


def find_cpf(text: str) -> str | None:
    match = _CPF_IN_TEXT.search(text)
    return _NON_DIGITS.sub("", match.group(1)) if match else None
