"""Small repository boundary. PostgreSQL (Supabase) in production; SQLite is an explicit local fallback."""

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

COLLECTIONS = [
    "users",
    "buildings",
    "meters",
    "readings",
    "bills",
    "alerts",
    "maintenanceTickets",
    "actionVerifications",
    "sustainabilitySnapshots",
    "settings",
]

# Postgres table names; collections not listed keep their own name.
TABLES = {
    "maintenanceTickets": "maintenance_tickets",
    "actionVerifications": "action_verifications",
    "sustainabilitySnapshots": "sustainability_snapshots",
}


class Store:
    kind = "sqlite-local"

    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS records (collection TEXT, id TEXT, body TEXT, PRIMARY KEY(collection,id))"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def all(self, c):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT body FROM records WHERE collection=?", (c,))
            ]

    def get(self, c, i):
        with self.connect() as db:
            r = db.execute(
                "SELECT body FROM records WHERE collection=? AND id=?", (c, i)
            ).fetchone()
            return json.loads(r[0]) if r else None

    def put(self, c, i, v):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO records VALUES(?,?,?)", (c, i, json.dumps(v))
            )

    def insert_many(self, c, rows):
        with self.connect() as db:
            for v in rows:
                db.execute(
                    "INSERT INTO records VALUES(?,?,?)", (c, v["id"], json.dumps(v))
                )


class PostgresStore:
    kind = "postgres"

    def __init__(self, url):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        # prepare_threshold=None: Supabase's transaction pooler cannot keep prepared statements.
        self.pool = ConnectionPool(
            url,
            min_size=1,
            max_size=4,
            kwargs={"prepare_threshold": None, "row_factory": dict_row},
            check=ConnectionPool.check_connection,
            open=True,
        )
        with self.pool.connection() as db:
            # Serialize concurrent cold starts applying the idempotent schema.
            db.execute("SELECT pg_advisory_xact_lock(74281)")
            db.execute(Path(__file__).with_name("schema.sql").read_text())

    @staticmethod
    def table(c):
        from psycopg import sql

        return sql.Identifier(TABLES.get(c, c))

    @staticmethod
    def plain(row):
        # Return dates and timestamps as the ISO strings the analytics and API expect.
        return {
            k: v.astimezone(timezone.utc).isoformat()
            if isinstance(v, datetime)
            else v.isoformat()
            if isinstance(v, date)
            else v
            for k, v in row.items()
        }

    def all(self, c):
        from psycopg import sql

        with self.pool.connection() as db:
            rows = db.execute(sql.SQL("SELECT * FROM {}").format(self.table(c)))
            return [self.plain(r) for r in rows]

    def get(self, c, i):
        from psycopg import sql

        with self.pool.connection() as db:
            r = db.execute(
                sql.SQL("SELECT * FROM {} WHERE id = %s").format(self.table(c)), (i,)
            ).fetchone()
            return self.plain(r) if r else None

    def write(self, db, c, v):
        from psycopg import sql
        from psycopg.types.json import Jsonb

        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            self.table(c),
            sql.SQL(", ").join(map(sql.Identifier, v)),
            sql.SQL(", ").join(sql.Placeholder() * len(v)),
        )
        db.execute(
            query, [Jsonb(x) if isinstance(x, (list, dict)) else x for x in v.values()]
        )

    def put(self, c, i, v):
        from psycopg import sql

        # Whole-record replace, matching the SQLite adapter.
        with self.pool.connection() as db:
            db.execute(
                sql.SQL("DELETE FROM {} WHERE id = %s").format(self.table(c)), (i,)
            )
            self.write(db, c, {**v, "id": i})

    def insert_many(self, c, rows):
        # One transaction: a duplicate rolls back the whole import.
        with self.pool.connection() as db:
            for v in rows:
                self.write(db, c, v)


def default_store(root):
    url = os.getenv("DATABASE_URL")
    if url:
        return PostgresStore(url)
    if os.getenv("APP_MODE", "production") == "local":
        return Store(os.getenv("LOCAL_DB_PATH", str(root / "data/local.sqlite")))
    raise RuntimeError("DATABASE_URL is required unless APP_MODE=local")
