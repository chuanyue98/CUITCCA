import sqlite3
from contextlib import closing

_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ip_visits (
    ip TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS endpoint_visits (
    endpoint TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    client_ip TEXT NOT NULL,
    email TEXT,
    message TEXT NOT NULL
);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    with closing(_connect(db_path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def flush_stats(db_path: str, stats: dict) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO access_stats (key, value) VALUES ('total_visits', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (stats.get('total_visits', 0),),
        )
        for ip, count in dict(stats.get('user_visits', {})).items():
            conn.execute(
                "INSERT INTO ip_visits (ip, count) VALUES (?, ?) "
                "ON CONFLICT(ip) DO UPDATE SET count = excluded.count",
                (ip, count),
            )
        for endpoint, count in dict(stats.get('endpoint_visits', {})).items():
            conn.execute(
                "INSERT INTO endpoint_visits (endpoint, count) VALUES (?, ?) "
                "ON CONFLICT(endpoint) DO UPDATE SET count = excluded.count",
                (endpoint, count),
            )
        conn.commit()


def load_stats(db_path: str) -> dict:
    with closing(_connect(db_path)) as conn:
        total_row = conn.execute(
            "SELECT value FROM access_stats WHERE key = 'total_visits'"
        ).fetchone()
        total_visits = total_row['value'] if total_row else 0
        user_visits = {
            row['ip']: row['count']
            for row in conn.execute("SELECT ip, count FROM ip_visits").fetchall()
        }
        endpoint_visits = {
            row['endpoint']: row['count']
            for row in conn.execute("SELECT endpoint, count FROM endpoint_visits").fetchall()
        }
    return {
        'total_visits': total_visits,
        'user_visits': user_visits,
        'endpoint_visits': endpoint_visits,
    }


def save_feedback(db_path: str, client_ip: str, email: str | None, message: str) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO feedback (client_ip, email, message) VALUES (?, ?, ?)",
            (client_ip, email, message),
        )
        conn.commit()


def list_feedback(db_path: str, limit: int = 100) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT created_at, client_ip, email, message FROM feedback "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
