import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Dialect, Enum
from sqlalchemy.types import TypeDecorator


def sa_enum(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class UtcDateTime(TypeDecorator[datetime]):
    """A moment in time, always stored as UTC and always read back with its UTC zone.

    SQLite keeps no time zone, so a plain DateTime(timezone=True) comes back without one, the API sends it with no
    offset, and browsers read it as their own local time (two hours early in Israel). Postgres keeps the zone; there
    this only turns any non-UTC value into UTC before it is written.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


JsonDict = dict[str, Any]
JsonList = list[Any]
