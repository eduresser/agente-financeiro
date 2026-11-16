import logging

import pytest

from banco_agil.logging_utils import get_logger, log_event, mask_cpf


@pytest.mark.parametrize("raw", ["123.456.789-00", "12345678900"])
def test_mask_cpf_keeps_only_middle_digits(raw: str) -> None:
    assert mask_cpf(raw) == "***.456.789-**"


def test_logged_cpf_never_appears_in_full(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("banco_agil.test")
    with caplog.at_level(logging.INFO, logger="banco_agil.test"):
        log_event(logger, "auth_failed", cpf="123.456.789-00", attempt=2)
        logger.warning("lookup for %s failed", "12345678900")
    text = caplog.text
    assert "***.456.789-**" in text
    assert "12345678900" not in text
    assert "123.456.789-00" not in text
