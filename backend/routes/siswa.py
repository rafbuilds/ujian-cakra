# backend/routes/siswa.py
from flask import Blueprint, request, jsonify
import uuid
from datetime import datetime, timezone, timedelta
from db import query
from auth import require_auth

siswa_bp = Blueprint('siswa', __name__)

# ── Device Registration ────────────────────────────────────────
@siswa_bp.route('/api/student/register-device', methods=['POST'])
@require_auth
def register_device():
    data = request.json or {}
    device_id   = data.get('device_id','').strip()
    device_info = data.get('device_info','').strip()
    if not device_id: return jsonify({'error': 'device_id wajib'}), 400
    user = query("SELECT device_id FROM users WHERE id=%s", (request.user_id,), fetch='one')
    if not user: return jsonify({'error': 'User tidak ditemukan'}), 404
    if user.get('device_id') and user['device_id'] != device_id:
        return jsonify({'allowed': False, 'error': 'Device tidak dikenali. Hubungi admin.'}), 403
    query("UPDATE users SET device_id=%s, device_info=%s WHERE id=%s",
          (device_id, device_info, request.user_id), fetch='none')
    return jsonify({'allowed': True})

# ── Exams List ─────────────────────────────────────────────────
@siswa_bp.route('/api/student/exams', methods=['GET'])
@require_auth
def student_exams():
    user = query("SELECT class_id FROM users WHERE id=%s", (request.user_id,), fetch='one')
    if not user or not user.get('class_id'):
        return jsonify([])
    rows = query("""
        SELECT e.id, e.title, e.duration_minutes, e.start_at, e.status,
               s.name as subject_name,
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) as question_count,
               (SELECT submitted_at FROM exam_sessions es
                WHERE es.exam_id=e.id AND es.student_id=%s LIMIT 1) as submitted_at,
               (SELECT id FROM exam_sessions es
                WHERE es.exam_id=e.id AND es.student_id=%s LIMIT 1) as session_id
        FROM exams e
        JOIN exam_classes ec ON ec.exam_id=e.id
        LEFT JOIN subjects s ON s.id=e.subject_id
        WHERE ec.class_id=%s AND e.status IN ('published','ongoing','finished')
        ORDER BY e.start_at DESC
    """, (request.user_id, request.user_id, user['class_id']))
    return jsonify([dict(r) for r in rows])

# ── Start Exam ─────────────────────────────────────────────────
@siswa_bp.route('/api/student/exams/<exam_id>/start', methods=['POST'])
@require_auth
def start_exam(exam_id):
    exam = query("SELECT * FROM exams WHERE id=%s", (exam_id,), fetch='one')
    if not exam: return jsonify({'error': 'Ujian tidak ditemukan'}), 404
    if exam['status'] not in ('published','ongoing'):
        return jsonify({'error': 'Ujian tidak tersedia'}), 400

    # Cek sesi existing
    existing = query("SELECT * FROM exam_sessions WHERE exam_id=%s AND student_id=%s",
                     (exam_id, request.user_id), fetch='one')
    if existing and existing.get('submitted_at'):
        return jsonify({'error': 'Ujian sudah dikumpulkan'}), 400

    # Aktifkan status ongoing
    if exam['status'] == 'published':
        query("UPDATE exams SET status='ongoing' WHERE id=%s", (exam_id,), fetch='none')

    if not existing:
        # Buat sesi baru
        session_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=int(exam.get('duration_minutes') or 90))
        token = uuid.uuid4().hex
        query("""INSERT INTO exam_sessions
                 (id, exam_id, student_id, token, device_key, ip_address, status, expires_at)
                 VALUES (%s,%s,%s,%s,%s,%s,'ongoing',%s)""",
              (session_id, exam_id, request.user_id, token,
               request.json.get('device_id') if request.json else None,
               request.remote_addr, expires_at), fetch='none')
    else:
        session_id = str(existing['id'])
        expires_at = existing.get('expires_at')

    # Ambil soal
    randomize_q = exam.get('randomize_questions', True)
    randomize_o = exam.get('randomize_options', True)
    order_clause = "ORDER BY RANDOM()" if randomize_q else "ORDER BY q.order_num"
    questions = query(f"""
        SELECT q.id, q.content, q.image_url FROM questions q
        WHERE q.exam_id=%s {order_clause}
    """, (exam_id,))

    result_questions = []
    for q in questions:
        opt_order = "ORDER BY RANDOM()" if randomize_o else "ORDER BY o.label"
        options = query(f"SELECT id, label, content FROM options o WHERE o.question_id=%s {opt_order}", (q['id'],))
        result_questions.append({**dict(q), 'options': [dict(o) for o in options]})

    # Ambil jawaban tersimpan
    saved = query("""SELECT question_id, option_id FROM answers WHERE session_id=%s""", (session_id,))
    saved_answers = {str(r['question_id']): str(r['option_id']) for r in saved if r['option_id']}

    now = datetime.now(timezone.utc)
    elapsed = 0
    if existing:
        started = existing.get('started_at')
        if started:
            if hasattr(started, 'tzinfo') and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = int((now - started).total_seconds())

    duration_secs = int(exam.get('duration_minutes') or 90) * 60
    remaining = max(0, duration_secs - elapsed)

    return jsonify({
        'session_id': session_id,
        'exam_id': exam_id,
        'questions': result_questions,
        'saved_answers': saved_answers,
        'remaining_seconds': remaining,
        'expires_at': expires_at.isoformat() if expires_at else None,
    })

# ── Answer ─────────────────────────────────────────────────────
@siswa_bp.route('/api/student/sessions/<session_id>/answer', methods=['POST'])
@require_auth
def save_answer(session_id):
    data = request.json or {}
    question_id = data.get('question_id')
    option_id   = data.get('option_id')
    if not question_id: return jsonify({'error': 'question_id wajib'}), 400
    sess = query("SELECT id FROM exam_sessions WHERE id=%s AND student_id=%s AND submitted_at IS NULL",
                 (session_id, request.user_id), fetch='one')
    if not sess: return jsonify({'error': 'Sesi tidak valid'}), 403
    existing = query("SELECT id FROM answers WHERE session_id=%s AND question_id=%s",
                     (session_id, question_id), fetch='one')
    if existing:
        query("UPDATE answers SET option_id=%s, answered_at=NOW() WHERE id=%s",
              (option_id, existing['id']), fetch='none')
    else:
        query("INSERT INTO answers (id, session_id, question_id, option_id) VALUES (%s,%s,%s,%s)",
              (str(uuid.uuid4()), session_id, question_id, option_id), fetch='none')
    return jsonify({'ok': True})

# ── Violation ──────────────────────────────────────────────────
@siswa_bp.route('/api/student/sessions/<session_id>/violation', methods=['POST'])
@require_auth
def record_violation(session_id):
    query("""UPDATE exam_sessions SET tab_violations=tab_violations+1
             WHERE id=%s AND student_id=%s""", (session_id, request.user_id), fetch='none')
    sess = query("SELECT tab_violations FROM exam_sessions WHERE id=%s", (session_id,), fetch='one')
    settings = query("SELECT max_violations FROM exam_settings LIMIT 1", fetch='one')
    max_v = settings['max_violations'] if settings else 5
    return jsonify({'violations': sess['tab_violations'] if sess else 0, 'max': max_v})

# ── Submit ─────────────────────────────────────────────────────
@siswa_bp.route('/api/student/sessions/<session_id>/submit', methods=['POST'])
@require_auth
def submit_exam(session_id):
    data        = request.json or {}
    auto_submit = data.get('auto_submit', False)
    sess = query("SELECT * FROM exam_sessions WHERE id=%s AND student_id=%s",
                 (session_id, request.user_id), fetch='one')
    if not sess: return jsonify({'error': 'Sesi tidak ditemukan'}), 404
    if sess.get('submitted_at'): return jsonify({'error': 'Sudah dikumpulkan'}), 400

    query("UPDATE exam_sessions SET submitted_at=NOW(), auto_submitted=%s WHERE id=%s",
          (auto_submit, session_id), fetch='none')

    exam_data = query("SELECT * FROM exams WHERE id=%s", (sess['exam_id'],), fetch='one')
    total_q = query("SELECT COUNT(*) as n FROM questions WHERE exam_id=%s",
                    (sess['exam_id'],), fetch='one')['n']
    correct = query("""SELECT COUNT(*) as n FROM answers a
                       JOIN options o ON o.id=a.option_id
                       WHERE a.session_id=%s AND o.is_correct=true""", (session_id,), fetch='one')['n']
    wrong   = query("""SELECT COUNT(*) as n FROM answers a
                       JOIN options o ON o.id=a.option_id
                       WHERE a.session_id=%s AND o.is_correct=false""", (session_id,), fetch='one')['n']
    empty   = total_q - correct - wrong
    spc     = float(exam_data.get('score_per_correct') or (100.0/total_q if total_q else 0))
    score   = round(correct * spc, 2)

    existing = query("SELECT id FROM results WHERE session_id=%s", (session_id,), fetch='one')
    if existing:
        query("UPDATE results SET score=%s,correct_count=%s,wrong_count=%s,empty_count=%s WHERE session_id=%s",
              (score, correct, wrong, empty, session_id), fetch='none')
    else:
        query("INSERT INTO results (id,session_id,score,correct_count,wrong_count,empty_count) VALUES (%s,%s,%s,%s,%s,%s)",
              (str(uuid.uuid4()), session_id, score, correct, wrong, empty), fetch='none')

    result = query("SELECT * FROM results WHERE session_id=%s", (session_id,), fetch='one')
    resp = {'ok': True, 'submitted_at': datetime.now(timezone.utc).isoformat()}
    if exam_data.get('show_result_after') and result:
        resp.update({'score': float(result['score']), 'correct_count': result['correct_count'],
                     'wrong_count': result['wrong_count'], 'empty_count': result['empty_count']})
    return jsonify(resp)

# ── Check Exit ─────────────────────────────────────────────────
@siswa_bp.route('/api/sessions/<session_id>/check-exit', methods=['GET'])
@require_auth
def check_exit(session_id):
    sess = query("SELECT exit_allowed FROM exam_sessions WHERE id=%s AND student_id=%s",
                 (session_id, request.user_id), fetch='one')
    if not sess: return jsonify({'allowed': False}), 404
    return jsonify({'allowed': bool(sess.get('exit_allowed'))})

# ── History ────────────────────────────────────────────────────
@siswa_bp.route('/api/siswa/<siswa_id>/history', methods=['GET'])
@require_auth
def siswa_history(siswa_id):
    rows = query("""
        SELECT es.*, e.title, s.name as subject_name, r.score, r.correct_count
        FROM exam_sessions es
        JOIN exams e ON e.id=es.exam_id
        LEFT JOIN subjects s ON s.id=e.subject_id
        LEFT JOIN results r ON r.session_id=es.id
        WHERE es.student_id=%s AND es.submitted_at IS NOT NULL
        ORDER BY es.submitted_at DESC
    """, (siswa_id,))
    return jsonify([dict(r) for r in rows])