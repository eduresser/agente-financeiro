import csv
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from banco_agil.domain.money import format_brl
from banco_agil.seed import bootstrap
from banco_agil.storage import CustomerRepository, LimitRequestRepository, ScoreLimitRepository
from banco_agil.tools.credit_tools import UNAVAILABLE, CreditService, build_credit_tools

ANA = "11144477735"
BRUNO = "52998224725"
NOW = datetime(2026, 11, 16, 9, 0, 0)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    bootstrap(tmp_path)
    return tmp_path


def make_service(data_dir: Path) -> CreditService:
    return CreditService(
        CustomerRepository(data_dir / "clientes.csv"),
        ScoreLimitRepository(data_dir / "score_limite.csv"),
        LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv"),
        clock=lambda: NOW,
    )


def write_customer(data_dir: Path, score: int, limit: str = "100.00") -> None:
    with (data_dir / "clientes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cpf", "nome", "data_nascimento", "limite_credito", "score_credito"])
        writer.writerow([ANA, "Ana Souza", "1990-05-17", limit, score])


def requests_rows(data_dir: Path) -> list[dict[str, str]]:
    return LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv").list_for(ANA)


def test_limit_query_shows_the_authenticated_customers_limit_only(data_dir: Path) -> None:
    text = make_service(data_dir).current_limit(ANA)
    assert "R$ 5.000,00" in text
    assert "1.000,00" not in text and "40.000,00" not in text


def test_approved_increase_is_recorded_and_applied(data_dir: Path) -> None:
    decision = make_service(data_dir).request_increase(ANA, Decimal("9000"))
    assert decision.status == "approved"
    assert requests_rows(data_dir) == [
        {
            "cpf_cliente": ANA,
            "data_hora_solicitacao": "2026-11-16T09:00:00",
            "limite_atual": "5000.00",
            "novo_limite_solicitado": "9000.00",
            "status_pedido": "aprovado",
        }
    ]
    assert CustomerRepository(data_dir / "clientes.csv").get(ANA).credit_limit == Decimal("9000")  # type: ignore[union-attr]


def test_rejected_increase_keeps_limit_and_stores_the_request(data_dir: Path) -> None:
    decision = make_service(data_dir).request_increase(BRUNO, Decimal("30000"))
    assert decision.status == "rejected"
    rows = LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv").list_for(BRUNO)
    assert [r["status_pedido"] for r in rows] == ["rejeitado"]
    assert rows[0]["novo_limite_solicitado"] == "30000.00"
    assert CustomerRepository(data_dir / "clientes.csv").get(BRUNO).credit_limit == Decimal("1000")  # type: ignore[union-attr]


@pytest.mark.parametrize("value", ["-100", "0", "NaN", "Infinity"])
def test_invalid_value_creates_no_request(data_dir: Path, value: str) -> None:
    decision = make_service(data_dir).request_increase(ANA, Decimal(value))
    assert decision.status == "invalid"
    assert requests_rows(data_dir) == []


@pytest.mark.parametrize("value", ["5000", "4000"])
def test_value_equal_or_below_current_is_refused_without_a_request_or_change(
    data_dir: Path, value: str
) -> None:
    decision = make_service(data_dir).request_increase(ANA, Decimal(value))
    assert decision.status == "invalid"
    assert "R$ 5.000,00" in decision.message
    assert requests_rows(data_dir) == []
    assert CustomerRepository(data_dir / "clientes.csv").get(ANA).credit_limit == Decimal("5000")  # type: ignore[union-attr]


def test_rejection_tells_the_ceiling_of_the_current_score(data_dir: Path) -> None:
    decision = make_service(data_dir).request_increase(BRUNO, Decimal("30000"))
    assert decision.status == "rejected"
    assert decision.ceiling == Decimal("1000.00")
    assert "R$ 1.000,00" in decision.message
    assert json.loads(decision.as_json())["max_allowed_limit"] == "1000.00"


@pytest.mark.parametrize(
    ("score", "ceiling"),
    [
        (0, 1000),
        (300, 1000),
        (301, 5000),
        (500, 5000),
        (501, 15000),
        (700, 15000),
        (701, 40000),
        (1000, 40000),
    ],
)
def test_ceiling_is_approved_and_one_cent_above_is_rejected(
    data_dir: Path, score: int, ceiling: int
) -> None:
    write_customer(data_dir, score)
    assert make_service(data_dir).request_increase(ANA, Decimal(ceiling)).status == "approved"
    write_customer(data_dir, score)
    above = Decimal(ceiling) + Decimal("0.01")
    assert make_service(data_dir).request_increase(ANA, above).status == "rejected"


FILES = ["clientes.csv", "score_limite.csv", "solicitacoes_aumento_limite.csv"]


@pytest.mark.parametrize("name", FILES)
def test_missing_base_gives_unavailability_message_and_logs(
    data_dir: Path, name: str, caplog: pytest.LogCaptureFixture
) -> None:
    (data_dir / name).unlink()
    service = make_service(data_dir)
    assert service.request_increase(ANA, Decimal("9000")).status == "unavailable"
    if name == "clientes.csv":
        assert service.current_limit(ANA) == UNAVAILABLE
    assert caplog.text
    assert ANA not in caplog.text


def test_tools_never_accept_a_cpf_and_only_touch_the_bound_customer(data_dir: Path) -> None:
    tools = {t.name: t for t in build_credit_tools(make_service(data_dir), ANA)}
    assert set(tools) == {"get_credit_limit", "request_limit_increase"}
    for tool in tools.values():
        assert set(tool.args) <= {"new_limit"}
    assert "R$ 5.000,00" in tools["get_credit_limit"].invoke({})
    before = (data_dir / "clientes.csv").read_text(encoding="utf-8").splitlines()
    result = json.loads(tools["request_limit_increase"].invoke({"new_limit": "9000"}))
    assert result["status"] == "approved"
    after = (data_dir / "clientes.csv").read_text(encoding="utf-8").splitlines()
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [1]


def test_brl_formatting() -> None:
    assert format_brl(Decimal("1234567.5")) == "R$ 1.234.567,50"
