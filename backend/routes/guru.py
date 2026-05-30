# backend/routes/guru.py
from flask import Blueprint, request, jsonify
import uuid
from db import query
from auth import require_guru, require_auth

guru_bp = Blueprint('guru', __name__)

# ── Taught Classes ─────────────────────────────────────────────
@guru_bp.route('/api/guru/taught-classes', methods=['GET'])
@require_guru
def get_taught_classes():
    rows = query("""
        SELECT c.* FROM classes c
        JOIN guru_classes gc ON gc.class_id=c.id
        WHERE gc.teacher_id=%s
        ORDER BY c.grade, LENGTH(c.id), c.id
    """, (request.user_id,))
    return jsonify([dict(r) for r in rows])

@guru_bp.route('/api/guru/taught-classes', methods=['POST'])
@require_guru
def add_taught_class():
    class_id = (request.json or {}).get('class_id','').strip()
    if not class_id: return jsonify({'error': 'class_id wajib'}), 400
    cls = query("SELECT id FROM classes WHERE id=%s", (class_id,), fetch='one')
    if not cls: return jsonify({'error': 'Kelas tidak ditemukan'}), 404
    query("INSERT INTO guru_classes (teacher_id, class_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
          (request.user_id, class_id), fetch='none')
    return jsonify({'ok': True})

@guru_bp.route('/api/guru/taught-classes/<class_id>', methods=['DELETE'])
@require_guru
def remove_taught_class(class_id):
    query("DELETE FROM guru_classes WHERE teacher_id=%s AND class_id=%s",
          (request.user_id, class_id), fetch='none')
    return jsonify({'ok': True})

# ── Subjects (Mapel per guru) ──────────────────────────────────
@guru_bp.route('/api/subjects', methods=['GET'])
@require_guru
def get_subjects():
    rows = query("""
        SELECT * FROM subjects
        WHERE teacher_id=%s OR teacher_id IS NULL
        ORDER BY name
    """, (request.user_id,))
    return jsonify([dict(r) for r in rows])

@guru_bp.route('/api/subjects', methods=['POST'])
@require_guru
def create_subject():
    name = (request.json or {}).get('name','').strip()
    if not name: return jsonify({'error': 'Nama mapel wajib'}), 400
    existing = query("SELECT id FROM subjects WHERE LOWER(name)=LOWER(%s) AND teacher_id=%s",
                     (name, request.user_id), fetch='one')
    if existing: return jsonify({'error': 'Mapel sudah ada'}), 409
    sub = query("INSERT INTO subjects (id, name, teacher_id) VALUES (%s,%s,%s) RETURNING *",
                (str(uuid.uuid4()), name, request.user_id), fetch='one')
    return jsonify(dict(sub)), 201

@guru_bp.route('/api/subjects/<subject_id>', methods=['PATCH'])
@require_guru
def update_subject(subject_id):
    name = (request.json or {}).get('name','').strip()
    if not name: return jsonify({'error': 'Nama wajib'}), 400
    query("UPDATE subjects SET name=%s WHERE id=%s AND teacher_id=%s",
          (name, subject_id, request.user_id), fetch='none')
    return jsonify(dict(query("SELECT * FROM subjects WHERE id=%s", (subject_id,), fetch='one')))

@guru_bp.route('/api/subjects/<subject_id>', methods=['DELETE'])
@require_guru
def delete_subject(subject_id):
    sub = query("SELECT * FROM subjects WHERE id=%s", (subject_id,), fetch='one')
    if not sub: return jsonify({'error': 'Tidak ditemukan'}), 404
    if str(sub.get('teacher_id','')) != request.user_id and request.user_role != 'admin':
        return jsonify({'error': 'Bukan mapel kamu'}), 403
    used = query("SELECT id FROM exams WHERE subject_id=%s LIMIT 1", (subject_id,), fetch='one')
    if used: return jsonify({'error': 'Mapel masih dipakai di ujian'}), 400
    query("DELETE FROM subjects WHERE id=%s", (subject_id,), fetch='none')
    return jsonify({'ok': True})

@guru_bp.route('/api/mapel-referensi', methods=['GET'])
@require_guru
def mapel_referensi():
    rows = query("SELECT DISTINCT name FROM subjects ORDER BY name")
    return jsonify([r['name'] for r in rows])

# ── Siswa (guru view) ──────────────────────────────────────────
@guru_bp.route('/api/guru/siswa', methods=['GET'])
@require_guru
def get_guru_siswa():
    rows = query("""
        SELECT u.*, c.name as class_name FROM users u
        LEFT JOIN classes c ON c.id=u.class_id
        WHERE u.role='siswa' AND u.class_id IN (
            SELECT class_id FROM guru_classes WHERE teacher_id=%s
        )
        ORDER BY c.grade, LENGTH(c.id), c.id, u.name
    """, (request.user_id,))
    return jsonify([dict(r) for r in rows])

@guru_bp.route('/api/guru/siswa/import', methods=['POST'])
@require_guru
def guru_import_siswa():
    from openpyxl import load_workbook
    file = request.files.get('file')
    if not file: return jsonify({'error': 'File tidak ada'}), 400
    wb = load_workbook(file); ws = wb.active
    imported = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]: continue
        name, nisn, class_id, email = (str(row[i] or '').strip() for i in range(4))
        if not name: continue
        dummy_gid = f"import_{uuid.uuid4().hex[:12]}"
        existing = query("SELECT id FROM users WHERE email=%s", (email,), fetch='one') if email else None
        if existing:
            query("UPDATE users SET name=%s, nisn=%s, class_id=%s WHERE id=%s",
                  (name, nisn or None, class_id or None, existing['id']), fetch='none')
        else:
            query("""INSERT INTO users (id, google_id, email, name, nisn, class_id, role, is_active)
                     VALUES (%s,%s,%s,%s,%s,%s,'siswa',true) ON CONFLICT (google_id) DO NOTHING""",
                  (str(uuid.uuid4()), dummy_gid, email or None, name, nisn or None, class_id or None), fetch='none')
        imported += 1
    return jsonify({'ok': True, 'imported': imported})

# ── Shared ─────────────────────────────────────────────────────
@guru_bp.route('/api/classes', methods=['GET'])
@require_auth
def get_classes():
    rows = query("SELECT * FROM classes ORDER BY grade, LENGTH(id), id")
    return jsonify([dict(r) for r in rows])

@guru_bp.route('/api/template-siswa', methods=['GET'])
@require_guru
def template_siswa():
    from flask import send_file
    from openpyxl import Workbook
    import io
    wb = Workbook(); ws = wb.active; ws.title = 'Data Siswa'
    ws.append(['Nama Lengkap','NISN','ID Kelas','Email'])
    ws.append(['Adi Saputra','0012345678','x_1','adi@sman1batangan.sch.id'])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='template_siswa.xlsx')

# ── Sessions (allow exit) ──────────────────────────────────────
@guru_bp.route('/api/sessions/<session_id>/allow-exit', methods=['POST'])
@require_guru
def allow_exit(session_id):
    query("UPDATE exam_sessions SET exit_allowed=true WHERE id=%s", (session_id,), fetch='none')
    return jsonify({'ok': True})