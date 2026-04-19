import os
import pymysql
import pymysql.cursors

DB_CFG = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 3306)),
    user     = os.getenv("DB_USER", "acore"),
    password = os.getenv("DB_PASS", "acore"),
    database = os.getenv("DB_NAME", "voice_assistant"),
    charset  = "utf8mb4",
    cursorclass = pymysql.cursors.DictCursor,
)


def get_db():
    return pymysql.connect(**DB_CFG)


def q1(sql, args=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()


def qall(sql, args=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()


def exe(sql, args=()):
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            conn.commit()
            return cur.lastrowid


def get_settings() -> dict:
    try:
        return {r["key_name"]: r["value"] for r in qall("SELECT key_name, value FROM settings")}
    except Exception:
        return {}


def get_provider(pid: int) -> dict | None:
    try:
        return q1("SELECT * FROM providers WHERE id=%s AND is_active=1", (pid,))
    except Exception:
        return None


def get_all_providers() -> list:
    try:
        return qall("SELECT * FROM providers WHERE is_active=1 ORDER BY name")
    except Exception:
        return []
