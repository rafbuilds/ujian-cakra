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
        ORDER BY c.name
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
    if getattr(request, 'user_role', '') == 'admin':
        rows = query("SELECT * FROM subjects ORDER BY name")
    else:
        rows = query(
            "SELECT * FROM subjects WHERE teacher_id=%s ORDER BY name",
            (request.user_id,)
        )
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
# FIX: return {students: [...]} bukan raw array, sesuai yang dibutuhkan frontend
@guru_bp.route('/api/guru/siswa', methods=['GET'])
@require_guru
def get_guru_siswa():
    # Cek apakah guru sudah assign kelas
    taught = query("SELECT class_id FROM guru_classes WHERE teacher_id=%s", (request.user_id,))
    
    if taught:
        # Guru sudah set kelas — tampilkan siswa dari kelas yang diajar saja
        rows = query("""
            SELECT
                u.id, u.name, u.email, u.nisn, u.class_id,
                c.name as class_name,
                ROUND(AVG(r.score)::numeric, 1) as avg_score
            FROM users u
            LEFT JOIN classes c ON c.id=u.class_id
            LEFT JOIN exam_sessions es ON es.student_id=u.id AND es.submitted_at IS NOT NULL
            LEFT JOIN results r ON r.session_id=es.id
            WHERE u.role='siswa' AND u.class_id IN (
                SELECT class_id FROM guru_classes WHERE teacher_id=%s
            )
            GROUP BY u.id, u.name, u.email, u.nisn, u.class_id, c.name
            ORDER BY c.name, u.name
        """, (request.user_id,))
    else:
        # Guru belum set kelas — tampilkan semua siswa
        rows = query("""
            SELECT
                u.id, u.name, u.email, u.nisn, u.class_id,
                c.name as class_name,
                ROUND(AVG(r.score)::numeric, 1) as avg_score
            FROM users u
            LEFT JOIN classes c ON c.id=u.class_id
            LEFT JOIN exam_sessions es ON es.student_id=u.id AND es.submitted_at IS NOT NULL
            LEFT JOIN results r ON r.session_id=es.id
            WHERE u.role='siswa'
            GROUP BY u.id, u.name, u.email, u.nisn, u.class_id, c.name
            ORDER BY c.name, u.name
        """)
    
    students = [dict(r) for r in rows]
    return jsonify({'students': students, 'total': len(students)})

@guru_bp.route('/api/guru/siswa/import', methods=['POST'])
@require_guru
def guru_import_siswa():
    from openpyxl import load_workbook
    file = request.files.get('file')
    if not file: return jsonify({'error': 'File tidak ada'}), 400
    wb = load_workbook(file); ws = wb.active
    saved = 0
    errors = []
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not row[0]: continue
        try:
            name = str(row[0] or '').strip()
            nisn = str(row[1] or '').strip()
            class_id = str(row[2] or '').strip() or None
            email = str(row[3] or '').strip() or None
            if not name: continue

            # Validasi kelas kalau ada
            if class_id:
                cls = query("SELECT id FROM classes WHERE id=%s", (class_id,), fetch='one')
                if not cls:
                    errors.append(f"Baris {idx}: Kelas '{class_id}' tidak ditemukan")
                    class_id = None

            existing = query("SELECT id FROM users WHERE email=%s", (email,), fetch='one') if email else None
            if existing:
                query("UPDATE users SET name=%s, nisn=%s, class_id=%s WHERE id=%s",
                      (name, nisn or None, class_id, existing['id']), fetch='none')
            else:
                dummy_gid = f"import_{uuid.uuid4().hex[:12]}"
                query("""INSERT INTO users (id, google_id, email, name, nisn, class_id, role, is_active)
                         VALUES (%s,%s,%s,%s,%s,%s,'siswa',true) ON CONFLICT (google_id) DO NOTHING""",
                      (str(uuid.uuid4()), dummy_gid, email, name, nisn or None, class_id), fetch='none')
            saved += 1
        except Exception as e:
            errors.append(f"Baris {idx}: {str(e)}")
    return jsonify({'ok': True, 'saved': saved, 'errors': errors})

# ── Riwayat ujian satu siswa ───────────────────────────────────
@guru_bp.route('/api/siswa/<student_id>/history', methods=['GET'])
@require_guru
def siswa_history(student_id):
    rows = query("""
        SELECT
            es.id, es.submitted_at, es.created_at,
            e.title as exam_title, e.id as exam_id,
            r.score, r.correct_count
        FROM exam_sessions es
        JOIN exams e ON e.id=es.exam_id
        LEFT JOIN results r ON r.session_id=es.id
        WHERE es.student_id=%s
        ORDER BY es.created_at DESC
    """, (student_id,))
    return jsonify({'history': [dict(r) for r in rows]})

# ── Classes (shared endpoint) ──────────────────────────────────
@guru_bp.route('/api/classes', methods=['GET'])
@require_auth
def get_classes():
    rows = query("SELECT * FROM classes ORDER BY name")
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
    ws.append(['Budi Santoso','0098765432','x_2','budi@sman1batangan.sch.id'])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='template_siswa.xlsx')

# ── Sessions (allow exit) ──────────────────────────────────────
@guru_bp.route('/api/sessions/<session_id>/allow-exit', methods=['POST'])
@require_guru
def allow_exit(session_id):
    query("UPDATE exam_sessions SET exit_allowed=true WHERE id=%s", (session_id,), fetch='none')
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
# EXAM GROUPS — Guru bisa join group ujian yang dibuat admin
# ══════════════════════════════════════════════════════════════

@guru_bp.route('/api/exam-groups', methods=['GET'])
@require_guru
def list_exam_groups():
    """
    Menampilkan semua group ujian yang dibuat admin.
    Termasuk info apakah guru sudah join atau belum.
    """
    try:
        rows = query("""
            SELECT eg.id, eg.name, eg.description, eg.created_at,
                   u.name as created_by_name,
                   COUNT(DISTINCT egm.teacher_id) as member_count,
                   COUNT(DISTINCT e.id) as exam_count,
                   BOOL_OR(egm.teacher_id = %s) as is_member
            FROM exam_groups eg
            LEFT JOIN users u ON u.id = eg.created_by
            LEFT JOIN exam_group_members egm ON egm.group_id = eg.id
            LEFT JOIN exams e ON e.group_id = eg.id
            WHERE eg.is_active = true
            GROUP BY eg.id, eg.name, eg.description, eg.created_at, u.name
            ORDER BY eg.created_at DESC
        """, (request.user_id,))
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])

@guru_bp.route('/api/exam-groups/<group_id>/join', methods=['POST'])
@require_guru
def join_exam_group(group_id):
    """Guru bergabung ke group ujian yang dibuat admin."""
    grp = query("SELECT id, name FROM exam_groups WHERE id=%s AND is_active=true",
                (group_id,), fetch='one')
    if not grp:
        return jsonify({'error': 'Group tidak ditemukan'}), 404

    existing = query("SELECT id FROM exam_group_members WHERE group_id=%s AND teacher_id=%s",
                     (group_id, request.user_id), fetch='one')
    if existing:
        return jsonify({'error': 'Sudah bergabung di group ini'}), 409

    query("""INSERT INTO exam_group_members (id, group_id, teacher_id, joined_at)
             VALUES (%s, %s, %s, NOW())""",
          (str(uuid.uuid4()), group_id, request.user_id), fetch='none')
    return jsonify({'ok': True, 'group_name': grp['name']})

@guru_bp.route('/api/exam-groups/<group_id>/leave', methods=['DELETE'])
@require_guru
def leave_exam_group(group_id):
    """Guru keluar dari group ujian."""
    query("DELETE FROM exam_group_members WHERE group_id=%s AND teacher_id=%s",
          (group_id, request.user_id), fetch='none')
    return jsonify({'ok': True})

@guru_bp.route('/api/exam-groups/my', methods=['GET'])
@require_guru
def my_exam_groups():
    """Group yang sudah diikuti oleh guru yang login."""
    try:
        rows = query("""
            SELECT eg.id, eg.name, eg.description,
                   COUNT(DISTINCT e.id) as exam_count, egm.joined_at
            FROM exam_groups eg
            JOIN exam_group_members egm ON egm.group_id = eg.id
            LEFT JOIN exams e ON e.group_id = eg.id
            WHERE egm.teacher_id = %s AND eg.is_active = true
            GROUP BY eg.id, eg.name, eg.description, egm.joined_at
            ORDER BY egm.joined_at DESC
        """, (request.user_id,))
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])