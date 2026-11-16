from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from banco_agil.storage.csv_store import StorageError, read_rows


@dataclass(frozen=True)
class ScoreBand:
    min_score: int
    max_score: int
    max_limit: Decimal


class ScoreLimitRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def bands(self) -> list[ScoreBand]:
        _, rows = read_rows(self._path)
        try:
            return [
                ScoreBand(
                    int(row["score_minimo"]),
                    int(row["score_maximo"]),
                    Decimal(row["limite_maximo"]),
                )
                for row in rows
            ]
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise StorageError(f"invalid score band row: {exc!r}") from exc

    def max_limit_for(self, score: int) -> Decimal:
        for band in self.bands():
            if band.min_score <= score <= band.max_score:
                return band.max_limit
        raise StorageError(f"no score band covers score {score}")
