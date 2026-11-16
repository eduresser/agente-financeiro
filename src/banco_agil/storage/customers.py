from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from banco_agil.storage.csv_store import StorageError, read_rows, write_rows_atomic


@dataclass(frozen=True)
class Customer:
    cpf: str
    name: str
    birth_date: date
    credit_limit: Decimal
    score: int


def _parse(row: dict[str, str]) -> Customer:
    try:
        return Customer(
            cpf=row["cpf"],
            name=row["nome"],
            birth_date=date.fromisoformat(row["data_nascimento"]),
            credit_limit=Decimal(row["limite_credito"]),
            score=int(row["score_credito"]),
        )
    except (KeyError, ValueError, InvalidOperation) as exc:
        raise StorageError(f"invalid customer row: {exc!r}") from exc


class CustomerRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, cpf: str) -> Customer | None:
        _, rows = read_rows(self._path)
        for row in rows:
            if row.get("cpf") == cpf:
                return _parse(row)
        return None

    def birth_date_of(self, cpf: str) -> date | None:
        customer = self.get(cpf)
        return customer.birth_date if customer else None

    def update_credit_limit(self, cpf: str, limit: Decimal) -> None:
        self._update(cpf, "limite_credito", f"{limit:.2f}")

    def update_score(self, cpf: str, score: int) -> None:
        self._update(cpf, "score_credito", str(score))

    def _update(self, cpf: str, column: str, value: str) -> None:
        fieldnames, rows = read_rows(self._path)
        for row in rows:
            if row.get("cpf") == cpf:
                row[column] = value
                write_rows_atomic(self._path, fieldnames, rows)
                return
        raise StorageError("customer not found")
