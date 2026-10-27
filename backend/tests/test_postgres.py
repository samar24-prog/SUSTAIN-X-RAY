"""Runs only when TEST_DATABASE_URL points at a disposable PostgreSQL database (tables are dropped)."""

import os
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.store import COLLECTIONS, TABLES, PostgresStore

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def store():
    import psycopg

    with psycopg.connect(URL) as db:
        for c in COLLECTIONS:
            db.execute(f'DROP TABLE IF EXISTS "{TABLES.get(c, c)}" CASCADE')
    s = PostgresStore(URL)
    yield s
    s.pool.close()


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("APP_MODE", "local")
    return TestClient(create_app(store))


def reading(category, value, start, end):
    return {
        "meter_id": "RO-" + category,
        "category": category,
        "unit": "L",
        "kind": "interval",
        "value": value,
        "start": start,
        "end": end,
        "source": "manual",
        "source_ref": "test logbook",
    }


def test_bills_round_trip(client, store):
    assert client.get("/api/health").json()["storage"] == "postgres"
    assert client.post("/api/seed").json()["count"] == 3
    assert client.post("/api/seed").status_code == 409
    d = client.get("/api/dashboard").json()
    assert d["latest"]["kwh"] == 3101811.4
    assert d["latest"]["period_end"] == "2026-08-31"
    assert d["bills"][1]["change_pct"] == pytest.approx(26.61173223865)
    assert len(d["alerts"]) == 1
    r = client.get("/api/export/bills?start=2026-06-01&end=2026-08-31")
    assert r.status_code == 200 and "3101811.4" in r.text


def test_readings_balance_and_atomic_import(client, store):
    day = ("2026-08-01T00:00:00+05:30", "2026-08-02T00:00:00+05:30")
    for c, v in [("ro_input", 100), ("ro_product", 60), ("ro_reject", 35)]:
        assert client.post("/api/readings", json=reading(c, v, *day)).status_code == 201
    stored = store.all("readings")[0]
    assert stored["end"] == "2026-08-01T18:30:00+00:00"
    assert stored["quality_flags"] == []
    b = client.get("/api/dashboard").json()["water"]["balances"][0]
    assert b["difference"] == 5 and b["recovery_pct"] == 60
    csv = (
        "meter_id,category,unit,kind,value,start,end,source_ref\n"
        "B1,block_1,L,interval,50,2026-08-02T00:00:00+05:30,2026-08-03T00:00:00+05:30,log\n"
        "RO-ro_input,ro_input,L,interval,100,2026-08-01T00:00:00+05:30,2026-08-02T00:00:00+05:30,log\n"
    )
    r = client.post("/api/import/readings", content=csv, headers={"Content-Type": "text/plain"})
    assert r.status_code == 409
    assert len(store.all("readings")) == 3


def test_unique_violation_rolls_back(store):
    import psycopg

    row = {"id": "a", "status": "open", "history": []}
    store.insert_many("alerts", [row])
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.insert_many("alerts", [{**row, "id": "b"}, row])
    assert [a["id"] for a in store.all("alerts")] == ["a"]


def test_workflow_settings_and_registry(client, store):
    t = {"title": "Inspect RO", "owner": "Operator", "status": "open"}
    tid = client.post("/api/tickets", json=t).json()["id"]
    a = reading("ro_input", 100, "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z")
    b = reading("ro_input", 80, "2026-08-02T00:00:00Z", "2026-08-03T00:00:00Z")
    ids = [client.post("/api/readings", json=x).json()["id"] for x in (a, b)]
    t.update(
        status="closed",
        findings="Valve inspected",
        corrective_action="Adjusted valve",
        post_start="2026-08-02T00:00:00Z",
        post_end="2026-08-03T00:00:00Z",
    )
    assert len(client.put("/api/tickets/" + tid, json=t).json()["history"]) == 2
    saved = store.get("maintenanceTickets", tid)
    assert saved["post_start"] == "2026-08-02T00:00:00+00:00" and saved["status"] == "closed"
    v = client.post(
        "/api/verifications",
        json={
            "ticket_id": tid,
            "baseline_ids": [ids[0]],
            "post_ids": [ids[1]],
            "evidence_type": "readings",
            "requested_status": "verified",
            "context": "Same operating hours and occupancy",
            "comparability_confirmed": True,
        },
    ).json()
    assert v["status"] == "verified" and v["reduction"] == 20
    assert store.get("actionVerifications", v["id"])["evidence_snapshot"][0]["value"] == 100
    s = client.get("/api/settings").json()
    s.update(increase_pct=30, marginal_kwh_rate=7.5, tariff_basis="Test tariff")
    assert client.put("/api/settings", json=s).status_code == 200
    assert client.get("/api/settings").json()["scenario_pcts"] == [2, 5, 10]
    assert client.get("/api/dashboard").json()["settings"]["increase_pct"] == 30
    user = {"name": "Admin", "role": "admin", "active": True}
    assert client.put("/api/registry/users/abc-123", json=user).status_code == 200
    assert client.get("/api/registry/users").json()[0]["role"] == "admin"
