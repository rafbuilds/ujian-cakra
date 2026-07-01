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

# Sekolah default — dibuat oleh migration_update.sql #27 untuk semua data
# lama (SMAN 1 Batangan). Dipakai sebagai fallback saat membuat user baru
# yang belum punya jalur penentuan sekolah eksplisit (mis. signup Google
# OAuth) — onboarding sekolah baru lewat super_admin akan punya school_id
# sendiri, bukan fallback ini.
DEFAULT_SCHOOL_ID  = "00000000-0000-0000-0000-000000000001"

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

# ── Subscription gate ────────────────────────────────────────
def subscription_block_reason(school_id):
    """None kalau sekolah ini boleh akses; string alasan kalau diblokir
    (di-suspend manual oleh super_admin, atau lisensi sudah lewat
    paid_until). school_id None (super_admin) selalu lolos."""
    if not school_id:
        return None
    school = query("SELECT is_active, paid_until FROM schools WHERE id=%s", (school_id,), fetch='one')
    if not school:
        return None  # sekolah lama sebelum tabel schools ada — jangan blokir
    if not school.get('is_active'):
        return 'Akun sekolah ini sedang dinonaktifkan. Hubungi admin platform.'
    paid_until = school.get('paid_until')
    if paid_until:
        from datetime import date
        if paid_until < date.today():
            return 'Lisensi sekolah ini sudah kedaluwarsa. Hubungi admin platform untuk perpanjangan.'
    return None

_FEATURE_COLUMNS = {
    'export':       'feature_export',
    'bank_soal':    'feature_bank_soal',
    'upload_media': 'feature_upload_media',
    'mobile':       'feature_mobile',
}

def feature_blocked_reason(school_id, feature):
    """None kalau fitur boleh dipakai; string alasan kalau super_admin sudah
    mematikan fitur ini untuk sekolah tsb lewat dashboard super admin.
    school_id None (super_admin sendiri) selalu lolos. Kolom dicek lewat
    whitelist _FEATURE_COLUMNS (bukan f-string langsung dari caller) supaya
    tidak ada celah nama kolom sembarangan masuk ke SQL."""
    if not school_id:
        return None
    col = _FEATURE_COLUMNS.get(feature)
    if not col:
        return None
    school = query(f"SELECT {col} FROM schools WHERE id=%s", (school_id,), fetch='one')
    if not school:
        return None  # sekolah lama sebelum kolom ini ada — jangan blokir
    if school.get(col) is False:
        return 'Fitur ini dinonaktifkan untuk sekolah Anda oleh admin platform.'
    return None

def validate_email_domain(school_id, email):
    """None kalau email boleh dipakai untuk sekolah ini; string alasan
    kalau ditolak. Hanya berlaku kalau super_admin sudah set
    schools.allowed_domain untuk sekolah ini — kalau belum diisi,
    semua domain email diterima (backward compatible)."""
    if not school_id or not email:
        return None
    school = query("SELECT allowed_domain FROM schools WHERE id=%s", (school_id,), fetch='one')
    domain = (school or {}).get('allowed_domain')
    if not domain:
        return None
    email_domain = email.strip().lower().split('@')[-1]
    if email_domain != domain.strip().lower():
        return f"Email harus menggunakan domain @{domain}"
    return None

# ── JWT ────────────────────────────────────────────────────
def create_token(user_id: str, role: str, school_id: str | None = None) -> str:
    payload = {
        "sub":       user_id,
        "role":      role,
        "school_id": school_id,  # None untuk super_admin (tidak terikat sekolah manapun)
        "exp":       datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
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
        request.school_id = payload.get("school_id")
        blocked = subscription_block_reason(request.school_id)
        if blocked:
            return jsonify({"error": blocked, "code": "subscription_blocked"}), 403
        return f(*args, **kwargs)
    return wrapper

def require_guru(f):
    """Guru, admin, dan super_admin."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Belum login"}), 401
        try:
            payload = decode_token(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Token tidak valid"}), 401
        if payload["role"] not in ("guru", "admin", "super_admin"):
            return jsonify({"error": "Akses ditolak"}), 403
        request.user_id   = payload["sub"]
        request.user_role = payload["role"]
        request.school_id = payload.get("school_id")
        blocked = subscription_block_reason(request.school_id)
        if blocked:
            return jsonify({"error": blocked, "code": "subscription_blocked"}), 403
        return f(*args, **kwargs)
    return wrapper

def require_admin(f):
    """Admin sekolah dan super_admin."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Belum login"}), 401
        try:
            payload = decode_token(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Token tidak valid"}), 401
        if payload["role"] not in ("admin", "super_admin"):
            return jsonify({"error": "Akses ditolak"}), 403
        request.user_id   = payload["sub"]
        request.user_role = payload["role"]
        request.school_id = payload.get("school_id")
        blocked = subscription_block_reason(request.school_id)
        if blocked:
            return jsonify({"error": blocked, "code": "subscription_blocked"}), 403
        return f(*args, **kwargs)
    return wrapper

def require_super_admin(f):
    """Hanya super_admin (pemilik platform) — kelola semua sekolah,
    billing, dan setting lintas-tenant. Sengaja TIDAK diturunkan dari
    require_admin supaya admin sekolah biasa tidak pernah bisa naik
    privilege ke endpoint super_admin walau ada bug di tempat lain."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Belum login"}), 401
        try:
            payload = decode_token(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Token tidak valid"}), 401
        if payload["role"] != "super_admin":
            return jsonify({"error": "Akses ditolak"}), 403
        request.user_id   = payload["sub"]
        request.user_role = payload["role"]
        request.school_id = None
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

        # Signup Google OAuth saat ini hanya untuk domain sekolah tunggal
        # (ALLOWED_DOMAIN) — belum ada pemilihan sekolah saat daftar, jadi
        # masuk ke sekolah default. Onboarding sekolah baru (lewat invite/
        # subdomain) ditangani terpisah oleh super_admin, tidak lewat jalur ini.
        import uuid
        query("""
            INSERT INTO users (id, google_id, email, name, avatar_url, role, is_active, school_id)
            VALUES (%s, %s, %s, %s, %s, %s, true, %s)
        """, (str(uuid.uuid4()), google_id, email, name, avatar, assigned_role, DEFAULT_SCHOOL_ID), fetch="none")

        user = query("SELECT * FROM users WHERE google_id=%s", (google_id,), fetch="one")

    token = create_token(str(user["id"]), user["role"], str(user["school_id"]) if user.get("school_id") else None)
    return {"user": dict(user), "token": token}