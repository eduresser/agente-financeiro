import logging

from banco_agil.domain.privacy import CPF_PLACEHOLDER, redact_sensitive


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.getMessage())
        record.args = None
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, SensitiveDataFilter) for f in logger.filters):
        logger.addFilter(SensitiveDataFilter())
    return logger


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: object
) -> None:
    parts = [event]
    for key, value in fields.items():
        text = CPF_PLACEHOLDER if key == "cpf" else redact_sensitive(str(value))
        parts.append(f"{key}={text}")
    logger.log(level, " ".join(parts))
