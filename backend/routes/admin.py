# backend/routes/admin.py
from flask import Blueprint, request, jsonify, send_file
import uuid, io
from db import query
from auth import require_admin, require_guru

admin_bp = Blueprint('admin', __name__)

# ── Users ──────────────────────────────────────────────────────
@admin_bp.route('/api/admin/users', methods=['GET'])
@require_admin
def get_users():
    rows = query("""
        SELECT id, email, name, role, avatar_url, last_login, device_id,
               created_at
        FROM users ORDER BY role, name
    """)
    return jsonify([dict(r) for r in rows])

@admin_bp.route('/api/admin/users/<user_id>', methods=['PATCH'])
@require_admin
def update_user(user_id):
    data = request.json or {}
    allowed = ['role', 'name', 'email']
    for f in [k for k in data if k in allowed]:
        query(f"UPDATE users SET {f}=%s WHERE id=%s", (data[f], user_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/users/<user_id>', methods=['DELETE'])
@require_admin
def delete_user(user_id):
    query("DELETE FROM users WHERE id=%s AND role!='admin'", (user_id,), fetch='none')
    return jsonify({'ok': True})

# ── Siswa ──────────────────────────────────────────────────────
@admin_bp.route('/api/admin/siswa', methods=['GET'])
@require_admin
def get_siswa():
    grade    = request.args.get('grade', '')
    class_id = request.args.get('class_id', '')
    search   = request.args.get('search', '')
    page     = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 50)), 200)

    where = ["u.role='siswa'"]
    params = []
    if grade:    where.append("c.grade=%s"); params.append(int(grade))
    if class_id: where.append("u.class_id=%s"); params.append(class_id)
    if search:   where.append("u.name ILIKE %s"); params.append(f'%{search}%')

    where_sql = ' AND '.join(where)
    total = query(f"""
        SELECT COUNT(*) as n FROM users u
        LEFT JOIN classes c ON c.id=u.class_id
        WHERE {where_sql}
    """, params, fetch='one')['n']

    rows = query(f"""
        SELECT u.id, u.name, u.email, u.nisn, u.class_id,
               c.name as class_name, c.grade,
               u.device_id, u.device_info, u.last_login, u.is_active
        FROM users u
        LEFT JOIN classes c ON c.id=u.class_id
        WHERE {where_sql}
        ORDER BY c.grade, LENGTH(c.id), c.id, u.name
        LIMIT %s OFFSET %s
    """, params + [per_page, (page-1)*per_page])

    return jsonify({'data': [dict(r) for r in rows], 'total': total, 'page': page})

@admin_bp.route('/api/admin/siswa/<siswa_id>', methods=['PATCH'])
@require_admin
def update_siswa(siswa_id):
    data = request.json or {}
    allowed = ['name', 'nisn', 'class_id', 'is_active']
    for f in [k for k in data if k in allowed]:
        query(f"UPDATE users SET {f}=%s WHERE id=%s AND role='siswa'",
              (data[f] or None, siswa_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/siswa/<siswa_id>', methods=['DELETE'])
@require_admin
def delete_siswa(siswa_id):
    query("DELETE FROM users WHERE id=%s AND role='siswa'", (siswa_id,), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/siswa/<siswa_id>/reset-device', methods=['POST'])
@require_admin
def reset_siswa_device(siswa_id):
    query("UPDATE users SET device_id=NULL, device_info=NULL WHERE id=%s AND role='siswa'",
          (siswa_id,), fetch='none')
    return jsonify({'ok': True, 'message': 'Device berhasil direset'})

@admin_bp.route('/api/admin/siswa/import', methods=['POST'])
@require_admin
def import_siswa():
    from openpyxl import load_workbook
    file = request.files.get('file')
    if not file: return jsonify({'error': 'File tidak ada'}), 400
    wb = load_workbook(file)
    ws = wb.active
    imported = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]: continue
        name, nisn, class_id, email = (str(row[i] or '').strip() for i in range(4))
        if not name: continue
        dummy_gid = f"import_{uuid.uuid4().hex[:12]}"
        existing = query("SELECT id FROM users WHERE email=%s AND role='siswa'", (email,), fetch='one') if email else None
        if existing:
            query("UPDATE users SET name=%s, nisn=%s, class_id=%s WHERE id=%s",
                  (name, nisn or None, class_id or None, existing['id']), fetch='none')
        else:
            query("""INSERT INTO users (id, google_id, email, name, nisn, class_id, role, is_active)
                     VALUES (%s,%s,%s,%s,%s,%s,'siswa',true)
                     ON CONFLICT (google_id) DO NOTHING""",
                  (str(uuid.uuid4()), dummy_gid, email or None, name, nisn or None, class_id or None), fetch='none')
        imported += 1
    return jsonify({'ok': True, 'imported': imported})

@admin_bp.route('/api/admin/siswa/template', methods=['GET'])
@require_admin
def siswa_template():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.title = 'Data Siswa'
    ws.append(['Nama Lengkap','NISN','ID Kelas','Email'])
    ws.append(['Contoh: Adi Saputra','0012345678','x_1','adi@sman1batangan.sch.id'])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='template_siswa.xlsx')

# ── Classes ────────────────────────────────────────────────────
@admin_bp.route('/api/admin/classes-detail', methods=['GET'])
@require_admin
def classes_detail():
    rows = query("""
        SELECT c.*, COUNT(u.id) as student_count
        FROM classes c LEFT JOIN users u ON u.class_id=c.id AND u.role='siswa'
        GROUP BY c.id ORDER BY c.grade, LENGTH(c.id), c.id
    """)
    return jsonify([dict(r) for r in rows])

# ── Subjects ───────────────────────────────────────────────────
@admin_bp.route('/api/admin/subjects', methods=['GET'])
@require_admin
def admin_get_subjects():
    rows = query("""
        SELECT s.*, u.name as teacher_name FROM subjects s
        LEFT JOIN users u ON u.id=s.teacher_id
        ORDER BY u.name, s.name
    """)
    return jsonify([dict(r) for r in rows])

# ── Guru Subjects & Classes ────────────────────────────────────
@admin_bp.route('/api/admin/guru/<guru_id>/subjects', methods=['GET'])
@require_admin
def admin_guru_subjects(guru_id):
    rows = query("SELECT * FROM subjects WHERE teacher_id=%s ORDER BY name", (guru_id,))
    return jsonify([dict(r) for r in rows])

@admin_bp.route('/api/admin/guru/<guru_id>/subjects', methods=['POST'])
@require_admin
def admin_add_guru_subject(guru_id):
    name = (request.json or {}).get('name','').strip()
    if not name: return jsonify({'error': 'Nama mapel wajib'}), 400
    existing = query("SELECT id FROM subjects WHERE LOWER(name)=LOWER(%s) AND teacher_id=%s",
                     (name, guru_id), fetch='one')
    if existing: return jsonify({'error': 'Mapel sudah ada'}), 409
    sub = query("INSERT INTO subjects (id, name, teacher_id) VALUES (%s,%s,%s) RETURNING *",
                (str(uuid.uuid4()), name, guru_id), fetch='one')
    return jsonify(dict(sub)), 201

@admin_bp.route('/api/admin/guru/<guru_id>/subjects/<subject_id>', methods=['DELETE'])
@require_admin
def admin_del_guru_subject(guru_id, subject_id):
    used = query("SELECT id FROM exams WHERE subject_id=%s LIMIT 1", (subject_id,), fetch='one')
    if used: return jsonify({'error': 'Mapel masih dipakai di ujian'}), 400
    query("DELETE FROM subjects WHERE id=%s AND teacher_id=%s", (subject_id, guru_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/guru/<guru_id>/classes', methods=['GET'])
@require_admin
def admin_guru_classes(guru_id):
    rows = query("""
        SELECT c.* FROM classes c JOIN guru_classes gc ON gc.class_id=c.id
        WHERE gc.teacher_id=%s ORDER BY c.grade, LENGTH(c.id), c.id
    """, (guru_id,))
    return jsonify([dict(r) for r in rows])

@admin_bp.route('/api/admin/guru/<guru_id>/classes', methods=['POST'])
@require_admin
def admin_add_guru_class(guru_id):
    class_id = (request.json or {}).get('class_id','').strip()
    if not class_id: return jsonify({'error': 'class_id wajib'}), 400
    query("INSERT INTO guru_classes (teacher_id, class_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
          (guru_id, class_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/guru/<guru_id>/classes/<class_id>', methods=['DELETE'])
@require_admin
def admin_del_guru_class(guru_id, class_id):
    query("DELETE FROM guru_classes WHERE teacher_id=%s AND class_id=%s",
          (guru_id, class_id), fetch='none')
    return jsonify({'ok': True})

# ── Exams (admin view) ─────────────────────────────────────────
@admin_bp.route('/api/admin/exams', methods=['GET'])
@require_admin
def admin_get_exams():
    rows = query("""
        SELECT e.*, u.name as teacher_name, s.name as subject_name,
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) as question_count,
               (SELECT STRING_AGG(c.name, ', ') FROM exam_classes ec JOIN classes c ON c.id=ec.class_id WHERE ec.exam_id=e.id) as class_names
        FROM exams e
        LEFT JOIN users u ON u.id=e.teacher_id
        LEFT JOIN subjects s ON s.id=e.subject_id
        ORDER BY e.created_at DESC
    """)
    return jsonify([dict(r) for r in rows])

@admin_bp.route('/api/admin/exams/<exam_id>', methods=['DELETE'])
@require_admin
def admin_delete_exam(exam_id):
    query("DELETE FROM exams WHERE id=%s", (exam_id,), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/exams/<exam_id>/force-finish', methods=['POST'])
@require_admin
def admin_force_finish(exam_id):
    ongoing = query("""
        SELECT id FROM exam_sessions WHERE exam_id=%s AND submitted_at IS NULL
    """, (exam_id,))
    exam_data = query("SELECT * FROM exams WHERE id=%s", (exam_id,), fetch='one')
    total_q = query("SELECT COUNT(*) as n FROM questions WHERE exam_id=%s", (exam_id,), fetch='one')['n']
    spc = float(exam_data.get('score_per_correct') or (100.0/total_q if total_q else 0))

    for sess in ongoing:
        sid = str(sess['id'])
        correct = query("""SELECT COUNT(*) as n FROM answers a JOIN options o ON o.id=a.option_id
                           WHERE a.session_id=%s AND o.is_correct=true""", (sid,), fetch='one')['n']
        wrong   = query("""SELECT COUNT(*) as n FROM answers a JOIN options o ON o.id=a.option_id
                           WHERE a.session_id=%s AND o.is_correct=false""", (sid,), fetch='one')['n']
        empty   = total_q - correct - wrong
        score   = round(correct * spc, 2)
        query("UPDATE exam_sessions SET submitted_at=NOW(), auto_submitted=true WHERE id=%s", (sid,), fetch='none')
        ex = query("SELECT id FROM results WHERE session_id=%s", (sid,), fetch='one')
        if ex:
            query("UPDATE results SET score=%s,correct_count=%s,wrong_count=%s,empty_count=%s WHERE session_id=%s",
                  (score, correct, wrong, empty, sid), fetch='none')
        else:
            query("INSERT INTO results (id,session_id,score,correct_count,wrong_count,empty_count) VALUES (%s,%s,%s,%s,%s,%s)",
                  (str(uuid.uuid4()), sid, score, correct, wrong, empty), fetch='none')

    query("UPDATE exams SET status='finished' WHERE id=%s", (exam_id,), fetch='none')
    return jsonify({'ok': True, 'submitted': len(ongoing)})

# ── Exam Settings ──────────────────────────────────────────────
@admin_bp.route('/api/admin/exam-settings', methods=['GET'])
@require_admin
def get_exam_settings():
    s = query("SELECT * FROM exam_settings LIMIT 1", fetch='one')
    return jsonify(dict(s) if s else {
        'passing_grade': 75, 'allow_remedial': True,
        'max_violations': 5, 'auto_submit_on_violation': True, 'show_ranking': True
    })

@admin_bp.route('/api/admin/exam-settings', methods=['PATCH'])
@require_admin
def update_exam_settings():
    data = request.json or {}
    existing = query("SELECT id FROM exam_settings LIMIT 1", fetch='one')
    if existing:
        fields = ', '.join(f"{k}=%s" for k in data)
        query(f"UPDATE exam_settings SET {fields} WHERE id=%s",
              list(data.values()) + [existing['id']], fetch='none')
    else:
        cols = ', '.join(data.keys()); vals = ', '.join(['%s']*len(data))
        query(f"INSERT INTO exam_settings ({cols}) VALUES ({vals})", list(data.values()), fetch='none')
    return jsonify({'ok': True})

# ── Rooms ──────────────────────────────────────────────────────
@admin_bp.route('/api/admin/rooms', methods=['GET'])
@require_admin
def get_rooms():
    rows = query("""
        SELECT r.*,
               u.name as created_by_name,
               COUNT(DISTINCT rt.teacher_id) as teacher_count,
               COUNT(DISTINCT rc.class_id) as class_count
        FROM rooms r
        LEFT JOIN users u ON u.id=r.created_by
        LEFT JOIN room_teachers rt ON rt.room_id=r.id
        LEFT JOIN room_classes rc ON rc.room_id=r.id
        GROUP BY r.id, u.name
        ORDER BY r.created_at DESC
    """)
    return jsonify([dict(r) for r in rows])

@admin_bp.route('/api/admin/rooms', methods=['POST'])
@require_admin
def create_room():
    data = request.json or {}
    name = data.get('name','').strip()
    if not name: return jsonify({'error': 'Nama room wajib'}), 400
    room = query("""
        INSERT INTO rooms (id, name, description, created_by)
        VALUES (%s,%s,%s,%s) RETURNING *
    """, (str(uuid.uuid4()), name, data.get('description',''), request.user_id), fetch='one')
    # Assign classes
    for cls in (data.get('class_ids') or []):
        query("INSERT INTO room_classes (room_id,class_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
              (str(room['id']), cls), fetch='none')
    # Assign teachers
    for tid in (data.get('teacher_ids') or []):
        query("INSERT INTO room_teachers (room_id,teacher_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
              (str(room['id']), tid), fetch='none')
    return jsonify(dict(room)), 201

@admin_bp.route('/api/admin/rooms/<room_id>', methods=['PATCH'])
@require_admin
def update_room(room_id):
    data = request.json or {}
    if 'name' in data:
        query("UPDATE rooms SET name=%s WHERE id=%s", (data['name'], room_id), fetch='none')
    if 'description' in data:
        query("UPDATE rooms SET description=%s WHERE id=%s", (data['description'], room_id), fetch='none')
    if 'is_active' in data:
        query("UPDATE rooms SET is_active=%s WHERE id=%s", (data['is_active'], room_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/rooms/<room_id>', methods=['DELETE'])
@require_admin
def delete_room(room_id):
    query("DELETE FROM rooms WHERE id=%s", (room_id,), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/rooms/<room_id>', methods=['GET'])
@require_admin
def get_room_detail(room_id):
    room = query("SELECT * FROM rooms WHERE id=%s", (room_id,), fetch='one')
    if not room: return jsonify({'error': 'Tidak ditemukan'}), 404
    teachers = query("""
        SELECT u.id, u.name, u.email, u.avatar_url FROM users u
        JOIN room_teachers rt ON rt.teacher_id=u.id
        WHERE rt.room_id=%s ORDER BY u.name
    """, (room_id,))
    classes = query("""
        SELECT c.* FROM classes c
        JOIN room_classes rc ON rc.class_id=c.id
        WHERE rc.room_id=%s ORDER BY c.grade, LENGTH(c.id), c.id
    """, (room_id,))
    exams = query("""
        SELECT e.*, u.name as teacher_name, s.name as subject_name,
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) as question_count
        FROM exams e
        JOIN users u ON u.id=e.teacher_id
        LEFT JOIN subjects s ON s.id=e.subject_id
        WHERE e.room_id=%s ORDER BY e.created_at DESC
    """, (room_id,))
    return jsonify({
        **dict(room),
        'teachers': [dict(t) for t in teachers],
        'classes': [dict(c) for c in classes],
        'exams': [dict(e) for e in exams],
    })

@admin_bp.route('/api/admin/rooms/<room_id>/teachers', methods=['POST'])
@require_admin
def add_room_teacher(room_id):
    teacher_id = (request.json or {}).get('teacher_id','')
    query("INSERT INTO room_teachers (room_id,teacher_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
          (room_id, teacher_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/rooms/<room_id>/teachers/<teacher_id>', methods=['DELETE'])
@require_admin
def remove_room_teacher(room_id, teacher_id):
    query("DELETE FROM room_teachers WHERE room_id=%s AND teacher_id=%s",
          (room_id, teacher_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/rooms/<room_id>/classes', methods=['POST'])
@require_admin
def add_room_class(room_id):
    class_id = (request.json or {}).get('class_id','')
    query("INSERT INTO room_classes (room_id,class_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
          (room_id, class_id), fetch='none')
    return jsonify({'ok': True})

@admin_bp.route('/api/admin/rooms/<room_id>/classes/<class_id>', methods=['DELETE'])
@require_admin
def remove_room_class(room_id, class_id):
    query("DELETE FROM room_classes WHERE room_id=%s AND class_id=%s",
          (room_id, class_id), fetch='none')
    return jsonify({'ok': True})

# ── Guru: lihat rooms yang dia ikuti ──────────────────────────
@admin_bp.route('/api/guru/rooms', methods=['GET'])
@require_guru
def get_guru_rooms():
    rows = query("""
        SELECT r.*, COUNT(DISTINCT rc.class_id) as class_count,
               COUNT(DISTINCT e.id) as exam_count
        FROM rooms r
        JOIN room_teachers rt ON rt.room_id=r.id AND rt.teacher_id=%s
        LEFT JOIN room_classes rc ON rc.room_id=r.id
        LEFT JOIN exams e ON e.room_id=r.id AND e.teacher_id=%s
        WHERE r.is_active=true
        GROUP BY r.id ORDER BY r.created_at DESC
    """, (request.user_id, request.user_id))
    return jsonify([dict(r) for r in rows])
