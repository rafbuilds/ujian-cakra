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

def count_correct_wrong(session_id, exam_id):
    """Hitung correct/wrong untuk soal single-choice (answers) + multiple_answer (multi_answers).
    Soal multiple_answer dianggap benar hanya jika pilihan siswa sama persis dengan kunci jawaban."""
    correct = query("""
        SELECT COUNT(*) as n FROM answers a
        JOIN options o ON o.id=a.option_id
        JOIN questions q ON q.id=a.question_id
        WHERE a.session_id=%s AND o.is_correct=true
          AND COALESCE(q.type,'multiple_choice') != 'multiple_answer'
    """, (session_id,), fetch='one')['n']
    wrong = query("""
        SELECT COUNT(*) as n FROM answers a
        JOIN options o ON o.id=a.option_id
        JOIN questions q ON q.id=a.question_id
        WHERE a.session_id=%s AND o.is_correct=false
          AND COALESCE(q.type,'multiple_choice') != 'multiple_answer'
    """, (session_id,), fetch='one')['n']

    multi_rows = query("""
        WITH student_sets AS (
            SELECT question_id, ARRAY_AGG(option_id ORDER BY option_id) as picked
            FROM multi_answers WHERE session_id=%s GROUP BY question_id
        ),
        correct_sets AS (
            SELECT q.id as question_id, ARRAY_AGG(o.id ORDER BY o.id) as correct
            FROM questions q JOIN options o ON o.question_id=q.id AND o.is_correct=true
            WHERE q.exam_id=%s AND COALESCE(q.type,'multiple_choice')='multiple_answer'
            GROUP BY q.id
        )
        SELECT ss.picked IS NOT NULL as answered,
               ss.picked IS NOT NULL AND ss.picked = cs.correct as is_correct
        FROM correct_sets cs LEFT JOIN student_sets ss ON ss.question_id=cs.question_id
    """, (session_id, exam_id))
    for r in multi_rows:
        if r['answered']:
            correct += 1 if r['is_correct'] else 0
            wrong   += 0 if r['is_correct'] else 1
    return correct, wrong