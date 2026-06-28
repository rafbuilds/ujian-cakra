"""
auth.py — Google OAuth & JWT session
"""
import os, threading, jwt, requests
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify
from werkzeug.security import generate_password_hash as _gen_hash, check_password_hash as _check_hash
from db import query

GOOGLE_TOKEN_URL   = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SECRET_KEY         = os.environ.get("SECRET_KEY", "dev-secret-key")
ALLOWED_DOMAIN     = os.environ.get("ALLOWED_DOMAIN", "sman1batangan.sch.id")
DEV_MODE           = os.environ.get("DEV_MODE", "false").lower() == "true"
TOKEN_HOURS        = 8  # sesi login expired 8 jam

# ── Password hashing ─────────────────────────────────────────
# Werkzeug versi baru default-nya pakai scrypt, yang sengaja boros memori
# (~32MB per verifikasi) untuk tahan brute-force. Itu aman untuk login
# satu-satu, tapi saat ratusan siswa login BERSAMAAN (mis. semua buka ujian
# di waktu yang sama), total kebutuhan memorinya bisa habiskan RAM server
# dan crash (malloc failure) — sudah terbukti lewat load test lokal.
# pbkdf2 nyaris tidak butuh memori ekstra (cuma CPU), jadi di beban tinggi
# dia cuma jadi lambat (request mengantri), bukan crash.
PASSWORD_HASH_METHOD = 'pbkdf2:sha256:260000'

# Tetap batasi jumlah verifikasi password yang dihitung BERSAMAAN — pbkdf2
# di iterasi segini cukup berat CPU (~150ms/operasi), jadi tanpa batas pun
# bisa membuat semua thread sibuk hash password dan request lain (load
# soal, dst) jadi keteteran kalau ratusan login nyerbu di detik yang sama.
_HASH_SEMAPHORE = threading.Semaphore(int(os.environ.get('PASSWORD_HASH_CONCURRENCY', '8')))

def hash_password(password: str) -> str:
    with _HASH_SEMAPHORE:
        return _gen_hash(password, method=PASSWORD_HASH_METHOD)

def verify_password(password_hash: str, password: str) -> bool:
    with _HASH_SEMAPHORE:
        return _check_hash(password_hash, password)

def needs_rehash(password_hash: str) -> bool:
    """True kalau hash masih pakai scheme lama (scrypt) yang boros memori."""
    return not (password_hash or '').startswith('pbkdf2:')

# ── JWT ────────────────────────────────────────────────────
def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub":  user_id,
        "role": role,
        "exp":  datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

def get_token_from_request() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("token")

# ── Middleware ──────────────────────────────────────────────
def require_auth(f):
    """Semua role yang sudah login."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Belum login"}), 401
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Sesi expired, silakan login ulang"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token tidak valid"}), 401
        request.user_id   = payload["sub"]
        request.user_role = payload["role"]
        return f(*args, **kwargs)
    return wrapper

def require_guru(f):
    """Hanya guru dan admin."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Belum login"}), 401
        try:
            payload = decode_token(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Token tidak valid"}), 401
        if payload["role"] not in ("guru", "admin"):
            return jsonify({"error": "Akses ditolak"}), 403
        request.user_id   = payload["sub"]
        request.user_role = payload["role"]
        return f(*args, **kwargs)
    return wrapper

def require_admin(f):
    """Hanya admin."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Belum login"}), 401
        try:
            payload = decode_token(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Token tidak valid"}), 401
        if payload["role"] != "admin":
            return jsonify({"error": "Akses ditolak"}), 403
        request.user_id   = payload["sub"]
        request.user_role = payload["role"]
        return f(*args, **kwargs)
    return wrapper

# ── Google OAuth helpers ────────────────────────────────────
def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    """Tukar authorization code dari Google → access token."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code":          code,
        "client_id":     os.environ.get("GOOGLE_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "redirect_uri":  redirect_uri,
        "grant_type":    "authorization_code",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_google_userinfo(access_token: str) -> dict:
    """Ambil info user dari Google (email, name, picture)."""
    resp = requests.get(GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    resp.raise_for_status()
    return resp.json()

def upsert_user(google_info: dict, requested_role: str = "siswa") -> dict:
    """
    Simpan atau update user di database.
    requested_role: role yang dipilih user saat login (guru/siswa/admin)
    Return: user dict + token JWT
    """
    email     = google_info.get("email", "")
    google_id = google_info.get("sub", "")
    name      = google_info.get("name", "")
    avatar    = google_info.get("picture", "")

    # Validasi domain sekolah
    if not DEV_MODE:
        domain = email.split("@")[-1]
        if domain != ALLOWED_DOMAIN:
            raise ValueError(f"Hanya akun @{ALLOWED_DOMAIN} yang diizinkan")

    # Cek apakah sudah ada di database
    user = query(
        "SELECT * FROM users WHERE google_id=%s OR email=%s",
        (google_id, email), fetch="one"
    )

    if user:
        # User sudah ada — update info terbaru
        query("""
            UPDATE users SET name=%s, avatar_url=%s, google_id=%s, last_login=NOW()
            WHERE id=%s
        """, (name, avatar, google_id, user["id"]), fetch="none")

        user = query("SELECT * FROM users WHERE id=%s", (user["id"],), fetch="one")

        if not user["is_active"]:
            raise ValueError("Akun dinonaktifkan. Hubungi admin sekolah.")

    else:
        # User baru — tentukan role berdasarkan requested_role
        if requested_role == "siswa":
            # Siswa harus sudah terdaftar — tidak boleh daftar sendiri
            raise ValueError(
                "Akun tidak terdaftar. Data siswa diinput oleh admin sekolah. "
                "Hubungi admin jika belum terdaftar."
            )
        elif requested_role == "guru":
            # Guru bisa daftar sendiri → status pending, tunggu approval admin
            assigned_role = "guru_pending"
        elif requested_role == "admin":
            raise ValueError("Pendaftaran admin tidak diizinkan melalui halaman ini.")
        else:
            assigned_role = "siswa"

        import uuid
        query("""
            INSERT INTO users (id, google_id, email, name, avatar_url, role, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, true)
        """, (str(uuid.uuid4()), google_id, email, name, avatar, assigned_role), fetch="none")

        user = query("SELECT * FROM users WHERE google_id=%s", (google_id,), fetch="one")

    token = create_token(str(user["id"]), user["role"])
    return {"user": dict(user), "token": token}