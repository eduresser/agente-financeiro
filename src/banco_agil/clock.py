from datetime import datetime
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")


def now_brasilia() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None)
