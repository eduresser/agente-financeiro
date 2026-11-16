import contextlib
import csv
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path


class StorageError(Exception):
    pass


def default_data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data"))


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise StorageError(f"{path.name} has no header")
            return list(reader.fieldnames), [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise StorageError(f"cannot read {path.name}: {exc}") from exc


def _copy_permissions(source: Path, target: str) -> None:
    try:
        info = source.stat()
    except FileNotFoundError:
        os.chmod(target, 0o644)
        return
    os.chmod(target, info.st_mode & 0o777)
    with contextlib.suppress(PermissionError, OSError):
        os.chown(target, info.st_uid, info.st_gid)


def write_rows_atomic(
    path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> None:
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: str(row[name]) for name in fieldnames})
            handle.flush()
            os.fsync(handle.fileno())
        _copy_permissions(path, tmp_name)
        os.replace(tmp_name, path)
        tmp_name = None
    except Exception as exc:
        raise StorageError(f"cannot write {path.name}: {exc}") from exc
    finally:
        if tmp_name is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
