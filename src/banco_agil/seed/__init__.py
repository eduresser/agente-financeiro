import logging
from pathlib import Path

from banco_agil.logging_utils import get_logger
from banco_agil.seed.data import DATASETS
from banco_agil.storage.csv_store import StorageError, write_rows_atomic

logger = get_logger(__name__)


def bootstrap(data_dir: Path) -> list[str]:
    created: list[str] = []
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        for name, (columns, rows) in DATASETS.items():
            path = data_dir / name
            if path.exists():
                continue
            write_rows_atomic(path, columns, [dict(zip(columns, row, strict=True)) for row in rows])
            created.append(name)
    except OSError as exc:
        logger.log(logging.ERROR, "bootstrap_failed directory=%s error=%s", data_dir, exc)
        raise StorageError(f"cannot prepare data directory {data_dir}") from exc
    if created:
        logger.info("bootstrap_created files=%s", ",".join(created))
    return created


__all__ = ["bootstrap"]
