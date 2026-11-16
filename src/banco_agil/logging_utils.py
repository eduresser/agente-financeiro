import logging
import re

_CPF_PATTERN = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")


def mask_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        return "***.***.***-**"
    return f"***.{digits[3:6]}.{digits[6:9]}-**"


def scrub(text: str) -> str:
    return _CPF_PATTERN.sub(lambda m: mask_cpf(m.group(0)), text)


class CpfMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.getMessage())
        record.args = None
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, CpfMaskingFilter) for f in logger.filters):
        logger.addFilter(CpfMaskingFilter())
    return logger


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: object
) -> None:
    parts = [event]
    for key, value in fields.items():
        text = mask_cpf(str(value)) if key == "cpf" else str(value)
        parts.append(f"{key}={text}")
    logger.log(level, " ".join(parts))
