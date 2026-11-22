import logging

import pytest

from banco_agil.logging_utils import get_logger, log_event

VALID_CPF = "529.982.247-25"


def test_logged_cpf_never_appears(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("banco_agil.test")
    with caplog.at_level(logging.INFO, logger="banco_agil.test"):
        log_event(logger, "auth_failed", cpf="123.456.789-00", attempt=2)
        log_event(logger, "lookup", detail=f"cpf {VALID_CPF}")
        logger.warning("lookup for %s failed", "52998224725")
    text = caplog.text
    assert "auth_failed cpf=[CPF] attempt=2" in text
    assert "lookup detail=cpf [CPF]" in text
    assert "lookup for [CPF] failed" in text
    for leaked in ("123.456.789-00", VALID_CPF, "52998224725", "982"):
        assert leaked not in text
