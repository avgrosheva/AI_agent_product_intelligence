"""Helper to build a Postgres-backed SQLAlchemy Enum column from a str-Enum.

Uses `values_callable` so the Postgres ENUM labels are the enum *values*
(e.g. "ru-RU") rather than the Python member names (e.g. "ru_ru", which
diverges from the value whenever the value isn't a valid Python
identifier). Applied uniformly so this class of bug can't reappear if a
future enum member's name and value diverge.
"""

from enum import EnumMeta

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: EnumMeta, name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, native_enum=True, values_callable=lambda x: [e.value for e in x])
