"""Times leave the API with their UTC offset, so a browser in Israel shows 13:14 and not 11:14."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, insert, select

from app.models.columns import UtcDateTime
from tests.test_smart_upload_and_real_estate import client  # noqa: F401  (the fixture)

ISRAEL_WINTER = timezone(timedelta(hours=2))


def test_sqlite_gives_back_the_same_moment_in_utc() -> None:
    metadata = MetaData()
    moments = Table("moments", metadata, Column("id", Integer, primary_key=True), Column("at", UtcDateTime()))
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    local = datetime(2026, 11, 20, 13, 14, tzinfo=ISRAEL_WINTER)
    naive_utc = datetime(2026, 11, 20, 11, 15)
    with engine.begin() as connection:
        connection.execute(insert(moments), [{"id": 1, "at": local}, {"id": 2, "at": naive_utc}, {"id": 3, "at": None}])
        rows = dict(connection.execute(select(moments.c.id, moments.c.at)).all())
    assert rows[1] == local and rows[1].utcoffset() == timedelta(0)
    assert rows[1].hour == 11
    assert rows[2] == naive_utc.replace(tzinfo=timezone.utc)
    assert rows[3] is None


def test_a_case_read_back_from_the_database_carries_its_offset(client: TestClient) -> None:  # noqa: F811
    created = client.post("/cases", json={"name": "Times", "process_key": "bl_6101", "client_name": "דנה"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    listed = client.get("/cases")
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == case_id)
    created_at = datetime.fromisoformat(row["created_at"])
    assert created_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(timezone.utc) - created_at) < timedelta(minutes=5)
