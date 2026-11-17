from pathlib import Path

import pytest

from banco_agil.domain.cpf import is_valid_cpf
from banco_agil.seed import bootstrap
from banco_agil.storage import (
    CustomerRepository,
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


def test_seeded_customers_have_valid_cpfs_and_band_edge_scores(tmp_path: Path) -> None:
    bootstrap(tmp_path)
    customers = CustomerRepository(tmp_path / "clientes.csv").all()
    bands = ScoreLimitRepository(tmp_path / "score_limite.csv")
    assert all(is_valid_cpf(c.cpf) for c in customers)
    for customer in customers:
        assert customer.credit_limit <= bands.max_limit_for(customer.score)
    assert {0, 300, 501, 700} <= {c.score for c in customers}


def test_unwritable_location_raises_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StorageError):
        bootstrap(blocker / "data")


def test_module_entrypoint_prepares_the_data_directory(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    env = {**os.environ, "DATA_DIR": str(tmp_path / "fresh")}
    result = subprocess.run(
        [sys.executable, "-m", "banco_agil.seed"], env=env, capture_output=True, check=False
    )
    assert result.returncode == 0
    assert sorted(p.name for p in (tmp_path / "fresh").iterdir()) == sorted(FILES)
