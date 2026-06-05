# backend/app.py — Entry point, import semua routes
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB max request body
_allowed_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', 'http://localhost:5000,http://localhost:8080').split(',') if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _allowed_origins}}, supports_credentials=True)

# ── Register Blueprints ────────────────────────────────────────
from routes.admin  import admin_bp
from routes.guru   import guru_bp
from routes.siswa  import siswa_bp
from routes.exams  import exams_bp

app.register_blueprint(admin_bp)
app.register_blueprint(guru_bp)
app.register_blueprint(siswa_bp)
app.register_blueprint(exams_bp)

# ── Auth Routes ────────────────────────────────────────────────
from auth import require_auth, require_admin, create_token
from werkzeug.security import generate_password_hash, check_password_hash

FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:8080')
DEV_MODE     = os.environ.get('DEV_MODE', 'false').lower() == 'true'

@app.route('/api/health')
def index():
    return jsonify({'status': 'ok', 'service': 'Ujian Online SMABA', 'dev_mode': DEV_MODE})

@app.route('/api/auth/login', methods=['POST'])
def login():
    from db import query
    body  = request.json or {}
    email = (body.get('email') or '').strip().lower()
    pw    = body.get('password') or ''
    if not email or not pw:
        return jsonify({'error': 'Email dan password wajib diisi'}), 400

    user = query("SELECT * FROM users WHERE LOWER(email)=%s AND is_active=true",
                 (email,), fetch='one')
    if not user:
        return jsonify({'error': 'Email tidak ditemukan atau akun nonaktif'}), 401

    ph = user.get('password_hash') or ''
    if not ph:
        return jsonify({'error': 'Password belum di-set. Hubungi admin sekolah.'}), 401
    if not check_password_hash(ph, pw):
        return jsonify({'error': 'Password salah'}), 401

    query("UPDATE users SET last_login=NOW() WHERE id=%s", (user['id'],), fetch='none')
    token = create_token(str(user['id']), user['role'])
    return jsonify({
        'token': token,
        'role':  user['role'],
        'name':  user['name'],
        'id':    str(user['id']),
    })

@app.route('/api/auth/device-login', methods=['POST'])
def device_login():
    """Login siswa menggunakan email + device fingerprint (tanpa password)."""
    from db import query
    body      = request.json or {}
    email     = (body.get('email') or '').strip().lower()
    device_id = (body.get('device_id') or '').strip()
    device_info = (body.get('device_info') or '').strip()[:250]

    if not email or not device_id:
        return jsonify({'error': 'Email dan device wajib'}), 400

    user = query(
        "SELECT * FROM users WHERE LOWER(email)=%s AND role='siswa' AND is_active=true",
        (email,), fetch='one'
    )
    if not user:
        return jsonify({'error': 'Akun siswa tidak ditemukan atau tidak aktif.\nHubungi admin sekolah.'}), 401

    existing_device = user.get('device_id')

    if not existing_device:
        # Pertama kali login → daftarkan device sekarang
        query("UPDATE users SET device_id=%s, device_info=%s, last_login=NOW() WHERE id=%s",
              (device_id, device_info, user['id']), fetch='none')
    elif existing_device != device_id:
        return jsonify({'error': 'HP ini tidak terdaftar.\nHubungi admin untuk reset perangkat.'}), 403
    else:
        query("UPDATE users SET last_login=NOW() WHERE id=%s", (user['id'],), fetch='none')

    token = create_token(str(user['id']), user['role'])
    return jsonify({
        'token': token,
        'role':  user['role'],
        'name':  user['name'],
        'id':    str(user['id']),
    })

@app.route('/api/auth/me')
@require_auth
def auth_me():
    from db import query
    user = query("SELECT id,email,name,role,avatar_url,class_id,nisn,last_login FROM users WHERE id=%s",
                 (request.user_id,), fetch='one')
    if not user: return jsonify({'error': 'User tidak ditemukan'}), 404
    return jsonify(dict(user))

@app.route('/api/auth/change-password', methods=['POST'])
@require_auth
def change_password():
    from db import query
    body   = request.json or {}
    old_pw = body.get('old_password', '')
    new_pw = body.get('new_password', '')
    if not new_pw or len(new_pw) < 6:
        return jsonify({'error': 'Password baru minimal 6 karakter'}), 400
    user = query("SELECT password_hash FROM users WHERE id=%s", (request.user_id,), fetch='one')
    if user and user.get('password_hash'):
        if not check_password_hash(user['password_hash'], old_pw):
            return jsonify({'error': 'Password lama salah'}), 401
    query("UPDATE users SET password_hash=%s WHERE id=%s",
          (generate_password_hash(new_pw), request.user_id), fetch='none')
    return jsonify({'ok': True})

# ── Dev Login ──────────────────────────────────────────────────
@app.route('/api/dev/login-as', methods=['POST'])
def dev_login():
    from db import query
    if not DEV_MODE: return jsonify({'error': 'Dev mode tidak aktif'}), 403
    email = (request.json or {}).get('email','')
    user  = query("SELECT * FROM users WHERE email=%s", (email,), fetch='one')
    if not user: return jsonify({'error': f'User {email} tidak ditemukan'}), 404
    query("UPDATE users SET last_login=NOW() WHERE id=%s", (user['id'],), fetch='none')
    token = create_token(str(user['id']), user['role'])
    return jsonify({'token': token, 'role': user['role'], 'name': user['name']})

# ══════════════════════════════════════════════════════════════
# ADMIN — Exam Groups (dibuat admin, guru bisa join)
# ══════════════════════════════════════════════════════════════
import uuid as _uuid

@app.route('/api/admin/exam-groups', methods=['GET'])
@require_admin
def admin_list_groups():
    from db import query
    rows = query("""
        SELECT eg.*, u.name as created_by_name,
               COUNT(DISTINCT egm.teacher_id) as member_count,
               COUNT(DISTINCT e.id) as exam_count
        FROM exam_groups eg
        LEFT JOIN users u ON u.id=eg.created_by
        LEFT JOIN exam_group_members egm ON egm.group_id=eg.id
        LEFT JOIN exams e ON e.group_id=eg.id
        GROUP BY eg.id, u.name
        ORDER BY eg.created_at DESC
    """, ())
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/exam-groups', methods=['POST'])
@require_admin
def admin_create_group():
    from db import query
    body = request.json or {}
    name = body.get('name','').strip()
    if not name: return jsonify({'error': 'Nama group wajib'}), 400
    grp = query("""
        INSERT INTO exam_groups (id, name, description, created_by, is_active)
        VALUES (%s,%s,%s,%s,true) RETURNING *
    """, (str(_uuid.uuid4()), name, body.get('description',''), request.user_id), fetch='one')
    return jsonify(dict(grp)), 201

@app.route('/api/admin/exam-groups/<group_id>', methods=['PATCH'])
@require_admin
def admin_update_group(group_id):
    from db import query
    body = request.json or {}
    query("UPDATE exam_groups SET name=%s, description=%s WHERE id=%s",
          (body.get('name',''), body.get('description',''), group_id), fetch='none')
    return jsonify({'ok': True})

@app.route('/api/admin/exam-groups/<group_id>', methods=['DELETE'])
@require_admin
def admin_delete_group(group_id):
    from db import query
    query("UPDATE exam_groups SET is_active=false WHERE id=%s", (group_id,), fetch='none')
    return jsonify({'ok': True})

@app.route('/api/admin/exam-groups/<group_id>/members', methods=['GET'])
@require_admin
def admin_group_members(group_id):
    from db import query
    rows = query("""
        SELECT u.id, u.name, u.email, egm.joined_at
        FROM exam_group_members egm
        JOIN users u ON u.id=egm.teacher_id
        WHERE egm.group_id=%s
        ORDER BY egm.joined_at DESC
    """, (group_id,))
    return jsonify([dict(r) for r in rows])

# ══════════════════════════════════════════════════════════════
# UPLOAD MEDIA — Lampiran & Audio untuk soal
# ══════════════════════════════════════════════════════════════
import base64, mimetypes
from werkzeug.utils import secure_filename

ALLOWED_ATTACH = {'png','jpg','jpeg','gif','webp','pdf'}
ALLOWED_AUDIO  = {'mp3','wav','ogg','m4a','aac'}
MAX_FILE_MB    = 10

def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

@app.route('/api/exams/<exam_id>/upload-media', methods=['POST'])
@require_auth
def upload_media(exam_id):
    from db import query as dbq
    file = request.files.get('file')
    ftype = request.form.get('type', 'attachment')  # 'attachment' | 'audio'
    if not file or not file.filename:
        return jsonify({'error': 'File tidak ada'}), 400

    ext = _ext(file.filename)
    allowed = ALLOWED_AUDIO if ftype == 'audio' else ALLOWED_ATTACH
    if ext not in allowed:
        return jsonify({'error': f'Format tidak diizinkan. Gunakan: {", ".join(allowed)}'}), 400

    data = file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        return jsonify({'error': f'Ukuran file maksimal {MAX_FILE_MB}MB'}), 400

    # Simpan sebagai base64 data URL (no external storage needed)
    mime = mimetypes.guess_type(file.filename)[0] or ('audio/mpeg' if ftype=='audio' else 'application/octet-stream')
    b64  = base64.b64encode(data).decode()
    url  = f"data:{mime};base64,{b64}"

    # Simpan ke DB (opsional — kalau tabel belum ada, tetap return URL)
    try:
        media_id = str(_uuid.uuid4())
        dbq("""INSERT INTO exam_media (id, exam_id, media_type, url, filename, uploaded_by, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,NOW())
               ON CONFLICT DO NOTHING""",
            (media_id, exam_id, ftype, url, secure_filename(file.filename), request.user_id),
            fetch='none')
    except Exception:
        media_id = None  # tabel belum ada, tidak masalah

    return jsonify({'ok': True, 'url': url, 'media_id': media_id})

# ══════════════════════════════════════════════════════════════
# CAMERA ESSAY — Siswa submit foto + uraian
# ══════════════════════════════════════════════════════════════
@app.route('/api/student/sessions/<session_id>/answer-essay', methods=['POST'])
@require_auth
def answer_essay(session_id):
    from db import query as dbq
    body = request.json or {}
    question_id = body.get('question_id')
    essay_text  = body.get('essay_text', '')
    photo_b64   = body.get('photo_b64', '')

    if not question_id:
        return jsonify({'error': 'question_id wajib'}), 400

    sess = dbq("SELECT id FROM exam_sessions WHERE id=%s AND student_id=%s AND submitted_at IS NULL",
               (session_id, request.user_id), fetch='one')
    if not sess:
        return jsonify({'error': 'Sesi tidak valid'}), 403

    dbq("""INSERT INTO essay_answers (id, session_id, question_id, essay_text, photo_b64, submitted_at)
           VALUES (%s,%s,%s,%s,%s,NOW())
           ON CONFLICT (session_id, question_id) DO UPDATE
           SET essay_text=%s, photo_b64=%s, submitted_at=NOW()""",
        (str(_uuid.uuid4()), session_id, question_id, essay_text, photo_b64, essay_text, photo_b64),
        fetch='none')

    # Juga simpan ke answers biasa (untuk tracking progress)
    dbq("""INSERT INTO answers (id, session_id, question_id, option_id, answered_at)
           VALUES (%s,%s,%s,'essay_submitted',NOW())
           ON CONFLICT (session_id, question_id) DO UPDATE SET option_id='essay_submitted', answered_at=NOW()""",
        (str(_uuid.uuid4()), session_id, question_id), fetch='none')

    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
# MULTI-ANSWER — Siswa pilih lebih dari 1 jawaban
# ══════════════════════════════════════════════════════════════
@app.route('/api/student/sessions/<session_id>/answer-multi', methods=['POST'])
@require_auth
def answer_multi(session_id):
    from db import query as dbq
    body = request.json or {}
    question_id = body.get('question_id')
    option_ids  = body.get('option_ids', [])

    if not question_id:
        return jsonify({'error': 'question_id wajib'}), 400

    sess = dbq("SELECT id FROM exam_sessions WHERE id=%s AND student_id=%s AND submitted_at IS NULL",
               (session_id, request.user_id), fetch='one')
    if not sess:
        return jsonify({'error': 'Sesi tidak valid'}), 403

    # Hapus jawaban lama untuk soal ini
    dbq("DELETE FROM multi_answers WHERE session_id=%s AND question_id=%s",
        (session_id, question_id), fetch='none')

    # Insert semua pilihan baru
    for oid in option_ids:
        dbq("""INSERT INTO multi_answers (id, session_id, question_id, option_id, answered_at)
               VALUES (%s,%s,%s,%s,NOW())""",
            (str(_uuid.uuid4()), session_id, question_id, oid), fetch='none')

    # Tracking di answers biasa
    dbq("""INSERT INTO answers (id, session_id, question_id, option_id, answered_at)
           VALUES (%s,%s,%s,%s,NOW())
           ON CONFLICT (session_id, question_id) DO UPDATE SET option_id=%s, answered_at=NOW()""",
        (str(_uuid.uuid4()), session_id, question_id, ','.join(option_ids), ','.join(option_ids)),
        fetch='none')

    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
# SERVE FRONTEND — Flask serve static files langsung
# Semua request non-API → serve dari folder static/
# ══════════════════════════════════════════════════════════════
import pathlib
from flask import send_from_directory, send_file

STATIC_DIR = pathlib.Path(__file__).parent / 'static'

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    # Jangan intercept API routes
    if path.startswith('api/'):
        return jsonify({'error': 'Not found'}), 404
    
    # Coba serve file langsung
    target = STATIC_DIR / path
    if target.is_file():
        return send_from_directory(str(STATIC_DIR), path)
    
    # Coba tambahkan .html
    if not path.endswith('.html'):
        html_target = STATIC_DIR / (path + '.html')
        if html_target.is_file():
            return send_from_directory(str(STATIC_DIR), path + '.html')
    
    # Fallback ke index.html (SPA behavior)
    index = STATIC_DIR / 'index.html'
    if index.is_file():
        return send_file(str(index))
    
    return jsonify({'error': 'Not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)),
            debug=DEV_MODE)