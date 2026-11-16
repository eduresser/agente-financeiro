from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from banco_agil.storage.csv_store import read_rows, write_rows_atomic

COLUMNS = [
    "cpf_cliente",
    "data_hora_solicitacao",
    "limite_atual",
    "novo_limite_solicitado",
    "status_pedido",
]


@dataclass(frozen=True)
class LimitRequest:
    cpf: str
    requested_at: datetime
    current_limit: Decimal
    requested_limit: Decimal
    status: str


class LimitRequestRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, request: LimitRequest) -> None:
        fieldnames, rows = read_rows(self._path)
        rows.append(
            {
                "cpf_cliente": request.cpf,
                "data_hora_solicitacao": request.requested_at.isoformat(timespec="seconds"),
                "limite_atual": f"{request.current_limit:.2f}",
                "novo_limite_solicitado": f"{request.requested_limit:.2f}",
                "status_pedido": request.status,
            }
        )
        write_rows_atomic(self._path, fieldnames or COLUMNS, rows)

    def list_for(self, cpf: str) -> list[dict[str, str]]:
        _, rows = read_rows(self._path)
        return [row for row in rows if row.get("cpf_cliente") == cpf]
