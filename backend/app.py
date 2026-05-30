# backend/app.py — Entry point, import semua routes
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

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
from auth import require_auth, require_admin, require_guru, create_token
import requests as http_requests

GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID','')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET','')
FRONTEND_URL         = os.environ.get('FRONTEND_URL','http://localhost:8080')
APP_URL              = os.environ.get('APP_URL','http://localhost:5000')
DEV_MODE             = os.environ.get('DEV_MODE','false').lower()=='true'
ALLOWED_DOMAIN       = os.environ.get('ALLOWED_DOMAIN','')

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'service': 'Ujian Online SMABA'})

@app.route('/api/auth/google/url')
def google_url():
    role = request.args.get('role','siswa')
    redirect_uri = f"{APP_URL}/api/auth/google/callback"
    url = (f"https://accounts.google.com/o/oauth2/v2/auth"
           f"?client_id={GOOGLE_CLIENT_ID}"
           f"&redirect_uri={redirect_uri}"
           f"&response_type=code"
           f"&scope=openid email profile"
           f"&state={role}")
    return jsonify({'url': url})

@app.route('/api/auth/google/callback')
def google_callback():
    from db import query
    import uuid
    code  = request.args.get('code')
    role  = request.args.get('state','siswa')
    redirect_uri = f"{APP_URL}/api/auth/google/callback"
    r = http_requests.post('https://oauth2.googleapis.com/token', data={
        'code': code, 'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'
    })
    if not r.ok: return jsonify({'error': 'Token exchange gagal'}), 400
    tokens = r.json()
    user_r = http_requests.get('https://www.googleapis.com/oauth2/v3/userinfo',
                                headers={'Authorization': f"Bearer {tokens['access_token']}"})
    if not user_r.ok: return jsonify({'error': 'Gagal ambil info user'}), 400
    info    = user_r.json()
    google_id = info['sub']
    email     = info.get('email','')
    name      = info.get('name','')
    avatar    = info.get('picture','')

    user = query("SELECT * FROM users WHERE google_id=%s", (google_id,), fetch='one')
    if not user:
        if ALLOWED_DOMAIN and not email.endswith('@'+ALLOWED_DOMAIN) and role == 'siswa':
            return f"<script>window.location='{FRONTEND_URL}?error=domain'</script>"
        # Guru masuk dulu sebagai guru_pending, admin aktivasi
        assigned_role = 'guru_pending' if role == 'guru' else role
        uid = str(uuid.uuid4())
        query("""INSERT INTO users (id, google_id, email, name, avatar_url, role, is_active)
                 VALUES (%s,%s,%s,%s,%s,%s,true)""",
              (uid, google_id, email, name, avatar, assigned_role), fetch='none')
        user = query("SELECT * FROM users WHERE id=%s", (uid,), fetch='one')

    query("UPDATE users SET last_login=NOW(), avatar_url=%s WHERE id=%s", (avatar, user['id']), fetch='none')
    token = create_token(str(user['id']), user['role'])

    # Redirect ke halaman yang sesuai role
    role_actual = user['role']
    if role_actual == 'guru_pending':
        dest = f"{FRONTEND_URL}/pages/guru-pending.html"
    elif role_actual == 'guru':
        dest = f"{FRONTEND_URL}/pages/guru-dashboard.html"
    elif role_actual == 'admin':
        dest = f"{FRONTEND_URL}/pages/admin-dashboard.html"
    else:
        dest = f"{FRONTEND_URL}/pages/siswa-ujian.html"

    return f"<script>localStorage.setItem('token','{token}');localStorage.setItem('user_role','{role_actual}');window.location='{dest}'</script>"

@app.route('/api/auth/me')
@require_auth
def auth_me():
    from db import query
    user = query("SELECT id,email,name,role,avatar_url,class_id,nisn,last_login FROM users WHERE id=%s",
                 (request.user_id,), fetch='one')
    if not user: return jsonify({'error': 'User tidak ditemukan'}), 404
    return jsonify(dict(user))

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)),
            debug=DEV_MODE)
