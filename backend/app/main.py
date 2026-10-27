import asyncio
from contextlib import asynccontextmanager, suppress
import csv
import hashlib
import io
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone, date
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import ValidationError
from .models import Bill, Reading, Ticket, Verification, Settings, Registry, UserRole
from .store import default_store
from .auth import identity, authorize
from .analytics import bill_metrics, water_analysis, alerts_for, verify, score
from .integrations import UnconfiguredAdapter
from .simulator import Simulator, SimulationConfig

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


def stable_id(collection, row):
    keys = (
        ["account", "invoice"]
        if collection == "bills"
        else ["meter_id", "category", "kind", "end"]
    )
    return hashlib.sha256(json.dumps([row[k] for k in keys]).encode()).hexdigest()[:32]


def stamped(row, user, id=None):
    return {
        **row,
        "id": id or uuid.uuid4().hex,
        "created_at": now(),
        "updated_at": now(),
        "created_by": user["uid"],
    }


def create_app(store=None):
    mode = os.getenv("APP_MODE", "production")
    if store is None:
        store = default_store(ROOT)
    simulator = Simulator()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(simulator.run())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Sustain-X-Ray", version="1.0.0", lifespan=lifespan)
    app.state.simulator = simulator
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            o.strip().rstrip("/")
            for o in os.getenv(
                "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
            ).split(",")
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def reader(user=Depends(identity)):
        return authorize(user, store)

    def writer(user=Depends(identity)):
        return authorize(user, store, ("operator", "admin"))

    def admin(user=Depends(identity)):
        return authorize(user, store, ("admin",))

    def settings():
        return {
            k: v
            for k, v in (
                store.get("settings", "global") or Settings().model_dump()
            ).items()
            if k in Settings.model_fields
        }

    def fail(e):
        raise HTTPException(422, str(e))

    def insert(collection, objects, user):
        rows = []
        for obj in objects:
            r = obj.model_dump(mode="json")
            i = stable_id(collection, r)
            if store.get(collection, i) or any(x["id"] == i for x in rows):
                raise HTTPException(409, "Duplicate record; no rows imported")
            if collection == "readings":
                r["end"] = (
                    datetime.fromisoformat(r["end"])
                    .astimezone(timezone.utc)
                    .isoformat()
                )
                if r.get("start"):
                    r["start"] = (
                        datetime.fromisoformat(r["start"])
                        .astimezone(timezone.utc)
                        .isoformat()
                    )
                i = stable_id(collection, r)
                if store.get(collection, i) or any(x["id"] == i for x in rows):
                    raise HTTPException(409, "Duplicate timestamp; no rows imported")
                if r["kind"] == "interval":
                    from .analytics import dt

                    for other in store.all(collection) + rows:
                        if (
                            other["meter_id"] == r["meter_id"]
                            and other["category"] == r["category"]
                            and other["kind"] == "interval"
                            and dt(r["start"]) < dt(other["end"])
                            and dt(other["start"]) < dt(r["end"])
                        ):
                            raise HTTPException(409, "Overlapping interval")
            if collection == "bills":
                for other in store.all(collection) + rows:
                    if (
                        other["account"] == r["account"]
                        and other["meter_id"] == r["meter_id"]
                        and r["period_start"] < other["period_end"]
                        and other["period_start"] < r["period_end"]
                    ):
                        raise HTTPException(409, "Overlapping billing period")
            rows.append(stamped(r, user, i))
        try:
            store.insert_many(collection, rows)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Duplicate record; transaction rolled back")
        except Exception as e:
            if type(e).__name__ == "UniqueViolation":
                raise HTTPException(409, "Duplicate record; transaction rolled back")
            raise
        return rows

    @app.get("/api/simulator")
    def simulator_status(user=Depends(reader)):
        # Serverless hosts pause the background loop between requests; catch up on poll.
        simulator.tick()
        return simulator.snapshot()

    @app.post("/api/simulator/start")
    def simulator_start(body: SimulationConfig, user=Depends(writer)):
        try:
            simulator.start(body)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return simulator.snapshot()

    @app.post("/api/simulator/pause")
    def simulator_pause(user=Depends(writer)):
        simulator.pause()
        return simulator.snapshot()

    @app.post("/api/simulator/reset")
    def simulator_reset(user=Depends(writer)):
        try:
            simulator.reset()
        except ValueError as e:
            raise HTTPException(409, str(e))
        return simulator.snapshot()

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": mode,
            "storage": store.kind,
            "hardware": UnconfiguredAdapter().health(),
        }

    @app.get("/api/me")
    def me(user=Depends(reader)):
        return {"uid": user["uid"], "role": user.get("role"), "mode": mode}

    @app.get("/api/dashboard")
    def dashboard(user=Depends(reader)):
        bills = store.all("bills")
        readings = store.all("readings")
        s = settings()
        water = water_analysis(readings, s)
        saved = {a["id"]: a for a in store.all("alerts")}
        generated = alerts_for(bills, water, s)
        alerts = [
            {**a, "status": saved.get(a["id"], {}).get("status", "open")}
            for a in generated
        ]
        verifications = store.all("actionVerifications")
        tickets = store.all("maintenanceTickets")
        for a in alerts:
            related = [t for t in tickets if t.get("alert_id") == a["id"]]
            a["tickets"] = [t["id"] for t in related]
            a["verification_status"] = (
                "verified"
                if any(
                    v["status"] == "verified" and v["ticket_id"] in a["tickets"]
                    for v in verifications
                )
                else "unverified"
            )
        metrics = bill_metrics(bills)
        real = [b for b in metrics if b["source"] != "demo" and not b["quality_flags"]]
        latest = real[-1] if real else None
        return {
            "bills": metrics,
            "water": water,
            "readings": readings,
            "alerts": alerts,
            "tickets": tickets,
            "verifications": verifications,
            "settings": s,
            "score": score(real, readings, verifications, s),
            "mode": mode,
            "freshness_days": (
                date.today() - date.fromisoformat(latest["period_end"])
            ).days
            if latest
            else None,
            "latest": latest,
            "hardware": UnconfiguredAdapter().health(),
            "scenarios": [
                {
                    "pct": p,
                    "kwh": latest["kwh"] * p / 100,
                    "estimated_inr": latest["kwh"] * p / 100 * s["marginal_kwh_rate"]
                    if s["marginal_kwh_rate"] is not None
                    else None,
                }
                for p in s["scenario_pcts"]
            ]
            if latest
            else [],
        }

    @app.post("/api/bills", status_code=201)
    def bill(body: Bill, user=Depends(writer)):
        return insert("bills", [body], user)[0]

    @app.post("/api/readings", status_code=201)
    def reading(body: Reading, user=Depends(writer)):
        if body.source == "actual":
            raise HTTPException(
                422,
                "Actual source reserved for commissioned hardware; use manual or imported",
            )
        return insert("readings", [body], user)[0]

    @app.post("/api/import/{collection}")
    def import_csv(
        collection: str,
        content: str = Body(media_type="text/plain"),
        user=Depends(writer),
    ):
        if collection not in ["bills", "readings"]:
            raise HTTPException(404)
        if len(content) > 1_000_000:
            raise HTTPException(413, "CSV limit is 1 MB")
        model = Bill if collection == "bills" else Reading
        try:
            reader_csv = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
            if not reader_csv.fieldnames or len(set(reader_csv.fieldnames)) != len(
                reader_csv.fieldnames
            ):
                raise ValueError("Missing or duplicate CSV headers")
            objects = []
            for n, row in enumerate(reader_csv, 2):
                if n > 201:
                    raise ValueError("Maximum 200 rows per import")
                row = {k: v for k, v in row.items() if v not in ["", None]}
                if "quality_flags" in row:
                    row["quality_flags"] = row["quality_flags"].split("|")
                if row.get("source") == "actual":
                    raise ValueError("CSV source cannot claim actual hardware readings")
                row["source"] = "demo" if row.get("source") == "demo" else "imported"
                try:
                    objects.append(model.model_validate(row))
                except ValidationError as e:
                    raise ValueError(f"Row {n}: {e}")
            if not objects:
                raise ValueError("CSV is empty")
        except (ValueError, csv.Error) as e:
            fail(e)
        rows = insert(collection, objects, user)
        return {"count": len(rows), "ids": [r["id"] for r in rows]}

    @app.post("/api/seed")
    def seed(user=Depends(admin)):
        return {
            "count": len(
                insert(
                    "bills",
                    [
                        Bill(**r)
                        for r in json.loads((ROOT / "data/bills.json").read_text())
                    ],
                    user,
                )
            )
        }

    @app.put("/api/alerts/{id}")
    def alert_status(id: str, status: str = Body(embed=True), user=Depends(writer)):
        if status not in ["open", "acknowledged", "resolved"]:
            raise HTTPException(422, "Invalid alert status")
        d = dashboard(user)
        if id not in [a["id"] for a in d["alerts"]]:
            raise HTTPException(404)
        old = store.get("alerts", id) or {"id": id, "history": []}
        old.update(
            status=status,
            updated_at=now(),
            history=old["history"]
            + [{"at": now(), "by": user["uid"], "status": status}],
        )
        store.put("alerts", id, old)
        return old

    @app.post("/api/tickets", status_code=201)
    def ticket(body: Ticket, user=Depends(writer)):
        if body.alert_id and body.alert_id not in [
            a["id"] for a in dashboard(user)["alerts"]
        ]:
            raise HTTPException(422, "Unknown alert")
        r = stamped(body.model_dump(mode="json"), user)
        r["history"] = [
            {"at": now(), "by": user["uid"], "record": body.model_dump(mode="json")}
        ]
        store.put("maintenanceTickets", r["id"], r)
        return r

    @app.put("/api/tickets/{id}")
    def update_ticket(id: str, body: Ticket, user=Depends(writer)):
        old = store.get("maintenanceTickets", id)
        if not old:
            raise HTTPException(404)
        if body.alert_id != old.get("alert_id"):
            raise HTTPException(422, "Alert association is immutable")
        r = {
            **old,
            **body.model_dump(mode="json"),
            "updated_at": now(),
            "history": old["history"]
            + [
                {"at": now(), "by": user["uid"], "record": body.model_dump(mode="json")}
            ],
        }
        store.put("maintenanceTickets", id, r)
        return r

    @app.post("/api/verifications", status_code=201)
    def verification(body: Verification, user=Depends(writer)):
        ticket = store.get("maintenanceTickets", body.ticket_id)
        if not ticket:
            raise HTTPException(422, "Unknown ticket")
        # A measurement may not be credited to multiple actions.
        if body.requested_status == "verified":
            used = {
                i
                for v in store.all("actionVerifications")
                if v["status"] == "verified"
                for i in v["post_ids"]
            }
            if used.intersection(body.post_ids):
                raise HTTPException(
                    409, "Post-action evidence already credited to a verified outcome"
                )
        try:
            result = verify(
                body.model_dump(),
                {r["id"]: r for r in store.all(body.evidence_type)},
                ticket,
            )
        except ValueError as e:
            fail(e)
        r = stamped(result, user)
        r["reviewed_by"] = user["uid"]
        store.insert_many("actionVerifications", [r])
        return r

    @app.get("/api/settings")
    def get_settings(user=Depends(reader)):
        return settings()

    @app.put("/api/settings")
    def update_settings(body: Settings, user=Depends(admin)):
        r = stamped(body.model_dump(), user, "global")
        store.put("settings", "global", r)
        return r

    @app.get("/api/registry/{collection}")
    def registry(collection: str, user=Depends(admin)):
        if collection not in ["users", "buildings", "meters"]:
            raise HTTPException(404)
        return store.all(collection)

    @app.put("/api/registry/{collection}/{id}")
    def put_registry(collection: str, id: str, body: dict, user=Depends(admin)):
        if collection not in ["users", "buildings", "meters"]:
            raise HTTPException(404)
        if not id or "/" in id or len(id) > 100:
            raise HTTPException(422, "Invalid ID")
        try:
            obj = (UserRole if collection == "users" else Registry).model_validate(body)
        except ValidationError as e:
            fail(e)
        if (
            collection == "users"
            and id == user["uid"]
            and (obj.role != "admin" or not obj.active)
        ):
            raise HTTPException(422, "Cannot remove your own administrative access")
        if collection == "meters" and obj.connectivity == "verified_adapter":
            raise HTTPException(422, "No adapter has been commissioned")
        r = stamped(obj.model_dump(), user, id)
        store.put(collection, id, r)
        return r

    @app.get("/api/reports")
    def reports(start: date = Query(...), end: date = Query(...), user=Depends(reader)):
        if end < start:
            raise HTTPException(422, "End precedes start")
        d = dashboard(user)
        return {
            "start": start,
            "end": end,
            "bills": [
                b for b in d["bills"] if str(start) <= b["period_end"] <= str(end)
            ],
            "readings": [
                r for r in d["readings"] if str(start) <= r["end"][:10] <= str(end)
            ],
            "verifications": [
                v
                for v in d["verifications"]
                if str(start) <= v["created_at"][:10] <= str(end)
            ],
            "filter_basis": "Bill period end, reading end and verification creation date; inclusive",
        }

    @app.get("/api/export/{collection}")
    def export(collection: str, start: date, end: date, user=Depends(reader)):
        d = reports(start, end, user)
        if collection not in ["bills", "readings", "verifications"]:
            raise HTTPException(404)
        rows = d[collection]
        output = io.StringIO()
        fields = list(rows[0]) if rows else ["id"]
        w = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            clean = {}
            for k, v in row.items():
                value = (
                    json.dumps(v)
                    if isinstance(v, (list, dict))
                    else str(v)
                    if v is not None
                    else ""
                )
                clean[k] = (
                    "'" + value
                    if value.startswith(("=", "+", "-", "@", "\t", "\r"))
                    else value
                )
            w.writerow(clean)
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{collection}.csv"'},
        )

    return app
