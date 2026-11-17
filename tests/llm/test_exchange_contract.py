from decimal import Decimal

import pytest

from banco_agil.config import Settings
from banco_agil.exchange import AwesomeApiProvider

pytestmark = pytest.mark.live

DEFAULT_URL = Settings.model_fields["exchange_api_base_url"].default


def test_real_api_still_answers_in_the_expected_format() -> None:
    provider = AwesomeApiProvider(DEFAULT_URL)

    dollar = provider.get_rate("USD")
    euro = provider.get_rate("euro")

    assert dollar.code == "USD" and dollar.rate > Decimal(0) and dollar.name
    assert euro.code == "EUR" and euro.rate > Decimal(0)
