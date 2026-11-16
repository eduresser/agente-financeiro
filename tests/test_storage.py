import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from banco_agil.storage import (
    CustomerRepository,
    LimitRequest,
    LimitRequestRepository,
    ScoreLimitRepository,
    StorageError,
)
from banco_agil.storage.csv_store import write_rows_atomic

DATA = Path(__file__).parent.parent / "data"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    for name in ("clientes.csv", "score_limite.csv", "solicitacoes_aumento_limite.csv"):
        shutil.copy(DATA / name, tmp_path / name)
    return tmp_path


def test_update_changes_only_the_target_customer(data_dir: Path) -> None:
    path = data_dir / "clientes.csv"
    before = path.read_text(encoding="utf-8").splitlines()
    CustomerRepository(path).update_score("11144477735", 720)
    after = path.read_text(encoding="utf-8").splitlines()
    changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert changed == [1]
    assert after[1] == "11144477735,Ana Souza,1990-05-17,5000.00,720"
    assert after[0] == before[0]


def test_credit_limit_update_is_persisted_with_two_decimals(data_dir: Path) -> None:
    repo = CustomerRepository(data_dir / "clientes.csv")
    repo.update_credit_limit("11144477735", Decimal("7500"))
    customer = repo.get("11144477735")
    assert customer is not None
    assert customer.credit_limit == Decimal("7500.00")
    assert repo.get("00000000000") is None


def test_failed_write_keeps_previous_content_readable(data_dir: Path) -> None:
    path = data_dir / "clientes.csv"
    original = path.read_text(encoding="utf-8")

    class Boom:
        def __str__(self) -> str:
            raise RuntimeError("disk failure")

    fieldnames = ["cpf", "nome", "data_nascimento", "limite_credito", "score_credito"]
    rows = [dict.fromkeys(fieldnames, "x"), {**dict.fromkeys(fieldnames, "y"), "nome": Boom()}]
    with pytest.raises(StorageError):
        write_rows_atomic(path, fieldnames, rows)
    assert path.read_text(encoding="utf-8") == original
    assert [p.name for p in data_dir.iterdir() if p.name.endswith(".tmp")] == []
    assert CustomerRepository(path).get("11144477735") is not None


def test_limit_request_row_has_all_columns_in_iso_format(data_dir: Path) -> None:
    repo = LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv")
    repo.append(
        LimitRequest(
            "11144477735",
            datetime(2026, 11, 16, 10, 30, 5),
            Decimal("5000"),
            Decimal("9000"),
            "aprovado",
        )
    )
    repo.append(
        LimitRequest(
            "11144477735",
            datetime(2026, 11, 16, 10, 40, 0),
            Decimal("5000"),
            Decimal("20000"),
            "rejeitado",
        )
    )
    assert repo.list_for("11144477735") == [
        {
            "cpf_cliente": "11144477735",
            "data_hora_solicitacao": "2026-11-16T10:30:05",
            "limite_atual": "5000.00",
            "novo_limite_solicitado": "9000.00",
            "status_pedido": "aprovado",
        },
        {
            "cpf_cliente": "11144477735",
            "data_hora_solicitacao": "2026-11-16T10:40:00",
            "limite_atual": "5000.00",
            "novo_limite_solicitado": "20000.00",
            "status_pedido": "rejeitado",
        },
    ]
    assert repo.list_for("52998224725") == []


@pytest.mark.parametrize(
    "name", ["clientes.csv", "score_limite.csv", "solicitacoes_aumento_limite.csv"]
)
def test_missing_or_unreadable_file_raises_storage_error(data_dir: Path, name: str) -> None:
    (data_dir / name).unlink()
    with pytest.raises(StorageError):
        {
            "clientes.csv": lambda p: CustomerRepository(p).get("11144477735"),
            "score_limite.csv": lambda p: ScoreLimitRepository(p).max_limit_for(500),
            "solicitacoes_aumento_limite.csv": lambda p: LimitRequestRepository(p).list_for("1"),
        }[name](data_dir / name)


def test_corrupted_customer_row_raises_storage_error(data_dir: Path) -> None:
    path = data_dir / "clientes.csv"
    path.write_bytes(b"cpf,nome,data_nascimento,limite_credito,score_credito\n1,A,notadate,x,y\n")
    with pytest.raises(StorageError):
        CustomerRepository(path).get("1")


def test_every_score_belongs_to_exactly_one_band(data_dir: Path) -> None:
    repo = ScoreLimitRepository(data_dir / "score_limite.csv")
    expected = {
        0: "1000.00",
        300: "1000.00",
        301: "5000.00",
        500: "5000.00",
        501: "15000.00",
        700: "15000.00",
        701: "40000.00",
        1000: "40000.00",
    }
    assert {score: str(repo.max_limit_for(score)) for score in expected} == expected
    with pytest.raises(StorageError):
        repo.max_limit_for(1001)
