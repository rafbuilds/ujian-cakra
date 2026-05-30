"""
db.py — Database connection dengan support DATABASE_URL (Supabase/Render)
"""
import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from urllib.parse import urlparse

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            # Parse DATABASE_URL dari Supabase/Render
            r = urlparse(database_url)
            _pool = pg_pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                host     = r.hostname,
                port     = r.port or 5432,
                dbname   = r.path.lstrip('/'),
                user     = r.username,
                password = r.password,
                sslmode  = 'require',
                cursor_factory = psycopg2.extras.RealDictCursor
            )
        else:
            # Local development fallback
            _pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                host     = os.environ.get("DB_HOST", "localhost"),
                port     = int(os.environ.get("DB_PORT", "5433")),
                dbname   = os.environ.get("DB_NAME", "ujian_smaba"),
                user     = os.environ.get("DB_USER", "postgres"),
                password = os.environ.get("DB_PASSWORD", "postgres"),
                cursor_factory = psycopg2.extras.RealDictCursor
            )
    return _pool

def get_db():
    return get_pool().getconn()

def release_db(conn):
    get_pool().putconn(conn)

def query(sql, params=None, fetch="all"):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        if fetch == "one":  return cur.fetchone()
        if fetch == "none": return None
        return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)