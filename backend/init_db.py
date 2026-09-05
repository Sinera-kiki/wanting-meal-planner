"""init_db.py — 幂等建表。install.sh 调用：python3 init_db.py（cwd = backend/）"""
import psycopg
from pathlib import Path


def load_db_props() -> dict[str, str]:
    import os
    return {
        "db.host": os.environ.get("APP_DB_HOST", ""),
        "db.port": os.environ.get("APP_DB_PORT", "5432"),
        "db.database": os.environ.get("APP_DB_NAME", ""),
        "db.username": os.environ.get("APP_DB_USER", ""),
        "db.password": os.environ.get("APP_DB_PASSWORD", ""),
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id          SERIAL PRIMARY KEY,
    owner_id    TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes (owner_id);

CREATE TABLE IF NOT EXISTS meal_plans (
    owner_id        TEXT        PRIMARY KEY,
    preferences     JSONB       NOT NULL,
    plan            JSONB       NOT NULL,
    checked_items   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    week_start      DATE        NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
"""


def main() -> None:
    p = load_db_props()
    if not p.get("db.host"):
        print("[init_db] APP_DB_* environment variables are missing — skipped")
        return
    with psycopg.connect(
        host=p["db.host"],
        port=int(p["db.port"]),
        dbname=p["db.database"],
        user=p["db.username"],
        password=p["db.password"],
    ) as conn:
        conn.execute(SCHEMA)
        conn.commit()
    print("[init_db] done")


if __name__ == "__main__":
    main()
