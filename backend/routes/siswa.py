# backend/routes/siswa.py
from flask import Blueprint, request, jsonify
import uuid, random
from datetime import datetime, timezone, timedelta
from db import query, count_correct_wrong
from auth import require_auth

siswa_bp = Blueprint('siswa', __name__)

# ── Device Registration ────────────────────────────────────────
@siswa_bp.route('/api/student/register-device', methods=['POST'])
@require_auth
def register_device():
    data = request.json or {}
    device_id     = data.get('device_id','').strip()
    device_info   = data.get('device_info','').strip()
    transfer_code = (data.get('transfer_code') or '').strip().upper()
    if not device_id: return jsonify({'error': 'device_id wajib'}), 400
    user = query("SELECT device_id FROM users WHERE id=%s", (request.user_id,), fetch='one')
    if not user: return jsonify({'error': 'User tidak ditemukan'}), 404
    if user.get('device_id') and user['device_id'] != device_id:
        # Device baru tidak dikenali — boleh lanjut kalau bawa kode pindah
        # device yang masih berlaku dari guru (HP lama mati/kuota habis).
        if transfer_code:
            code_row = query("""
                SELECT id FROM device_transfer_codes
                WHERE student_id=%s AND code=%s AND used_at IS NULL AND expires_at > NOW()
            """, (request.user_id, transfer_code), fetch='one')
            if not code_row:
                return jsonify({'allowed': False, 'error': 'Kode pindah device salah atau sudah kedaluwarsa.'}), 403
            query("UPDATE device_transfer_codes SET used_at=NOW() WHERE id=%s", (code_row['id'],), fetch='none')
        else:
            return jsonify({
                'allowed': False,
                'error': 'Device tidak dikenali. Minta guru pengawas membuka akses lewat Pengawas Live (scan/kode), atau hubungi admin.',
            }), 403
    query("UPDATE users SET device_id=%s, device_info=%s WHERE id=%s",
          (device_id, device_info, request.user_id), fetch='none')
    return jsonify({'allowed': True})

@siswa_bp.route('/api/student/my-unlock-code', methods=['GET'])
@require_auth
def my_unlock_code():
    """Kode/barcode tetap milik siswa ini — dipakai guru di Pengawas Live
    untuk membuka device baru kalau HP lama siswa mati/kuota habis."""
    user = query("SELECT unlock_code FROM users WHERE id=%s", (request.user_id,), fetch='one')
    if not user: return jsonify({'error': 'User tidak ditemukan'}), 404
    code = user.get('unlock_code')
    if not code:
        import random as _r, string as _s
        for _ in range(5):
            candidate = ''.join(_r.choices(_s.ascii_uppercase + _s.digits, k=8))
            exists = query("SELECT 1 FROM users WHERE unlock_code=%s", (candidate,), fetch='one')
            if not exists:
                code = candidate
                break
        query("UPDATE users SET unlock_code=%s WHERE id=%s", (code, request.user_id), fetch='none')
    return jsonify({'unlock_code': code})

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
        now_utc    = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(minutes=int(exam.get('duration_minutes') or 90))
        token = uuid.uuid4().hex
        query("""INSERT INTO exam_sessions
                 (id, exam_id, student_id, token, device_key, ip_address, status, started_at, expires_at)
                 VALUES (%s,%s,%s,%s,%s,%s,'ongoing',%s,%s)""",
              (session_id, exam_id, request.user_id, token,
               request.json.get('device_id') if request.json else None,
               request.remote_addr, now_utc, expires_at), fetch='none')
    else:
        session_id = str(existing['id'])
        expires_at = existing.get('expires_at')
        # Reset exit_allowed saat siswa masuk kembali setelah keluar sementara
        query("UPDATE exam_sessions SET exit_allowed=FALSE, status='ongoing' WHERE id=%s",
              (session_id,), fetch='none')

    # Ambil soal — dengan auto-deteksi type dari data (fix untuk soal lama tanpa type)
    randomize_q = exam.get('randomize_questions', True)
    randomize_o = exam.get('randomize_options', True)
    order_clause = "ORDER BY RANDOM()" if randomize_q else "ORDER BY q.order_num"
    questions = query(f"""
        SELECT q.id, q.content, q.image_url,
               q.type, q.attachment_url, q.audio_url, q.max_choices,
               (SELECT COUNT(*) FROM options WHERE question_id=q.id) AS opt_count,
               (SELECT COUNT(*) FROM options WHERE question_id=q.id AND is_correct=true) AS correct_count
        FROM questions q
        WHERE q.exam_id=%s {order_clause}
    """, (exam_id,))

    # Jawaban esai & multi-jawaban yang sudah tersimpan — supaya bisa
    # direstore di frontend kalau siswa reload/buka ulang halaman ujian.
    saved_essays = query("SELECT question_id, essay_text FROM essay_answers WHERE session_id=%s", (session_id,))
    essay_map = {str(r['question_id']): r['essay_text'] for r in saved_essays}
    saved_multi = query("SELECT question_id, option_id FROM multi_answers WHERE session_id=%s", (session_id,))
    multi_map = {}
    for r in saved_multi:
        multi_map.setdefault(str(r['question_id']), []).append(str(r['option_id']))

    # Ambil semua opsi sekaligus (satu query, bukan per-soal) lalu kelompokkan.
    all_opts = query("""SELECT o.id, o.label, o.content, o.image_url, o.question_id FROM options o
                        JOIN questions q ON q.id=o.question_id WHERE q.exam_id=%s ORDER BY o.label""",
                     (exam_id,))
    opts_by_question = {}
    for o in all_opts:
        opts_by_question.setdefault(str(o['question_id']), []).append(dict(o))
    if randomize_o:
        for opts in opts_by_question.values():
            random.shuffle(opts)

    result_questions = []
    for q in questions:
        options = opts_by_question.get(str(q['id']), [])
        q_dict = dict(q)
        opt_count     = q_dict.pop('opt_count', 0) or 0
        correct_count = q_dict.pop('correct_count', 0) or 0
        # Auto-deteksi type jika belum di-set
        if not q_dict.get('type') or q_dict['type'] == 'multiple_choice':
            if q_dict.get('audio_url'):
                q_dict['type'] = 'audio'
            elif opt_count == 0:
                q_dict['type'] = 'camera_essay'
            elif correct_count > 1:
                q_dict['type'] = 'multiple_answer'
            else:
                q_dict['type'] = 'multiple_choice'
        if q_dict['type'] == 'multiple_answer' and not q_dict.get('max_choices'):
            q_dict['max_choices'] = correct_count or 1
        q_dict['essay_text'] = essay_map.get(str(q['id']))
        q_dict['saved_option_ids'] = multi_map.get(str(q['id']), [])
        result_questions.append({**q_dict, 'options': options})

    # Ambil jawaban tersimpan
    saved = query("""SELECT question_id, option_id FROM answers WHERE session_id=%s""", (session_id,))
    saved_answers = {str(r['question_id']): str(r['option_id']) for r in saved if r['option_id']}

    now = datetime.now(timezone.utc)

    # Prioritaskan expires_at jika ada (untuk sesi yang dibuka ulang oleh guru)
    # expires_at di-set saat reopen → akurat untuk sesi reset/perpanjangan
    expires_at_val = (existing or {}).get('expires_at') or expires_at
    if expires_at_val:
        if hasattr(expires_at_val, 'tzinfo') and expires_at_val.tzinfo is None:
            expires_at_val = expires_at_val.replace(tzinfo=timezone.utc)
        remaining = max(0, int((expires_at_val - now).total_seconds()))
    else:
        # Fallback: hitung dari started_at + durasi (sesi normal)
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
        'expires_at': expires_at_val.isoformat() if expires_at_val else (expires_at.isoformat() if expires_at else None),
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

# ── Essay / Kamera ─────────────────────────────────────────────
@siswa_bp.route('/api/student/sessions/<session_id>/answer-essay', methods=['POST'])
@require_auth
def save_essay_answer(session_id):
    data        = request.json or {}
    question_id = data.get('question_id')
    essay_text  = data.get('essay_text', '') or ''
    photo_b64   = data.get('photo_b64', '') or None  # simpan NULL jika kosong
    if not question_id:
        return jsonify({'error': 'question_id wajib'}), 400
    sess = query(
        "SELECT id FROM exam_sessions WHERE id=%s AND student_id=%s AND submitted_at IS NULL",
        (session_id, request.user_id), fetch='one')
    if not sess:
        return jsonify({'error': 'Sesi tidak valid'}), 403
    existing = query(
        "SELECT id FROM essay_answers WHERE session_id=%s AND question_id=%s",
        (session_id, question_id), fetch='one')
    if existing:
        query("UPDATE essay_answers SET essay_text=%s, photo_b64=%s WHERE id=%s",
              (essay_text, photo_b64, existing['id']), fetch='none')
    else:
        query("""INSERT INTO essay_answers (id, session_id, question_id, essay_text, photo_b64)
                 VALUES (%s,%s,%s,%s,%s)""",
              (str(uuid.uuid4()), session_id, question_id, essay_text, photo_b64), fetch='none')
    return jsonify({'ok': True})

# ── Multi-answer (pilih lebih dari 1) ──────────────────────────
@siswa_bp.route('/api/student/sessions/<session_id>/answer-multi', methods=['POST'])
@require_auth
def save_multi_answer(session_id):
    data        = request.json or {}
    question_id = data.get('question_id')
    option_ids  = data.get('option_ids', [])
    if not question_id:
        return jsonify({'error': 'question_id wajib'}), 400
    sess = query(
        "SELECT id FROM exam_sessions WHERE id=%s AND student_id=%s AND submitted_at IS NULL",
        (session_id, request.user_id), fetch='one')
    if not sess:
        return jsonify({'error': 'Sesi tidak valid'}), 403
    q = query("SELECT max_choices, type FROM questions WHERE id=%s", (question_id,), fetch='one')
    if q and q.get('type') == 'multiple_answer' and q.get('max_choices'):
        if len(option_ids) > q['max_choices']:
            return jsonify({'error': f"Maksimal {q['max_choices']} jawaban"}), 400
    # Hapus pilihan lama lalu insert ulang
    query("DELETE FROM multi_answers WHERE session_id=%s AND question_id=%s",
          (session_id, question_id), fetch='none')
    for opt_id in option_ids:
        query("""INSERT INTO multi_answers (id, session_id, question_id, option_id)
                 VALUES (%s,%s,%s,%s)""",
              (str(uuid.uuid4()), session_id, question_id, opt_id), fetch='none')
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
    correct, wrong = count_correct_wrong(session_id, sess['exam_id'])
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
    # Siswa hanya bisa lihat riwayatnya sendiri; guru/admin bisa lihat semua
    if request.user_role == 'siswa' and siswa_id != request.user_id:
        return jsonify({'error': 'Akses ditolak'}), 403
    rows = query("""
        SELECT es.id, es.exam_id, es.submitted_at, es.auto_submitted, es.tab_violations,
               e.title, s.name as subject_name, r.score, r.correct_count,
               r.wrong_count, r.empty_count
        FROM exam_sessions es
        JOIN exams e ON e.id=es.exam_id
        LEFT JOIN subjects s ON s.id=e.subject_id
        LEFT JOIN results r ON r.session_id=es.id
        WHERE es.student_id=%s AND es.submitted_at IS NOT NULL
        ORDER BY es.submitted_at DESC
    """, (siswa_id,))
    return jsonify([dict(r) for r in rows])