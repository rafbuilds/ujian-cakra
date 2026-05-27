"""
db.py — Database connection helper
Fallback ke simple connection jika pool gagal
"""
import os
import psycopg2
import psycopg2.extras

def _get_config():
    return dict(
        host     = os.environ.get("DB_HOST", "localhost"),
        port     = os.environ.get("DB_PORT", "5433"),
        dbname   = os.environ.get("DB_NAME", "ujian_smaba"),
        user     = os.environ.get("DB_USER", "postgres"),
        password = os.environ.get("DB_PASSWORD", "postgres"),
        cursor_factory = psycopg2.extras.RealDictCursor
    )

# Connection pool
_pool = None

def get_pool():
    global _pool
    if _pool is None:
        from psycopg2 import pool as pg_pool
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=2, maxconn=10,
            **_get_config()
        )
    return _pool

def get_db():
    try:
        return get_pool().getconn()
    except Exception:
        # Fallback: koneksi langsung
        return psycopg2.connect(**_get_config())

def release_db(conn):
    try:
        get_pool().putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass

def query(sql, params=None, fetch="all"):
    conn = None
    use_pool = True
    try:
        pool = get_pool()
        conn = pool.getconn()
    except Exception:
        use_pool = False
        conn = psycopg2.connect(**_get_config())

    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        if fetch == "one":  return cur.fetchone()
        if fetch == "none": return None
        return cur.fetchall()
    finally:
        if conn:
            if use_pool:
                try:
                    get_pool().putconn(conn)
                except Exception:
                    conn.close()
            else:
                conn.close()