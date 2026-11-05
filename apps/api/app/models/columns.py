import enum
import uuid
from typing import Any

from sqlalchemy import Enum


def sa_enum(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


JsonDict = dict[str, Any]
JsonList = list[Any]
