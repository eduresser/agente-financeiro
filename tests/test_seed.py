from datetime import date
from pathlib import Path

import pytest

from banco_agil.domain.cpf import is_valid_cpf
from banco_agil.seed import bootstrap
from banco_agil.storage import (
    CustomerRepository,
    LimitRequestRepository,
    ScoreLimitRepository,
    StorageError,
)

FILES = ["clientes.csv", "score_limite.csv", "solicitacoes_aumento_limite.csv"]


def test_missing_directory_is_created_with_all_three_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "data"
    assert sorted(bootstrap(target)) == sorted(FILES)
    assert sorted(p.name for p in target.iterdir()) == sorted(FILES)


def test_existing_files_are_never_overwritten_and_only_missing_ones_are_created(
    tmp_path: Path,
) -> None:
    bootstrap(tmp_path)
    customers = tmp_path / "clientes.csv"
    CustomerRepository(customers).update_score("11144477735", 999)
    edited = customers.read_text(encoding="utf-8")
    (tmp_path / "score_limite.csv").unlink()

    assert bootstrap(tmp_path) == ["score_limite.csv"]
    assert customers.read_text(encoding="utf-8") == edited
    assert bootstrap(tmp_path) == []


def test_seeded_customers_are_valid_and_include_band_edge_scores(tmp_path: Path) -> None:
    bootstrap(tmp_path)
    customers = CustomerRepository(tmp_path / "clientes.csv").all()
    bands = ScoreLimitRepository(tmp_path / "score_limite.csv")
    assert len(customers) == 6
    assert all(is_valid_cpf(c.cpf) for c in customers)
    assert all(c.birth_date < date.today() for c in customers)
    for customer in customers:
        assert customer.credit_limit <= bands.max_limit_for(customer.score)
    assert {0, 300, 501, 700} <= {c.score for c in customers}


def test_request_history_starts_empty_but_readable(tmp_path: Path) -> None:
    bootstrap(tmp_path)
    assert LimitRequestRepository(tmp_path / "solicitacoes_aumento_limite.csv").list_for("1") == []


def test_unwritable_location_raises_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StorageError):
        bootstrap(blocker / "data")
