# backend/routes/exams.py
from flask import Blueprint, request, jsonify, send_file
import uuid, io
from db import query
from auth import require_guru, require_auth, require_admin

exams_bp = Blueprint('exams', __name__)

# ── CRUD Ujian ─────────────────────────────────────────────────
@exams_bp.route('/api/exams', methods=['GET'])
@require_guru
def get_exams():
    rows = query("""
        SELECT e.*, s.name as subject_name,
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) as question_count,
               (SELECT STRING_AGG(c.name,', ') FROM exam_classes ec
                JOIN classes c ON c.id=ec.class_id WHERE ec.exam_id=e.id) as class_names
        FROM exams e
        LEFT JOIN subjects s ON s.id=e.subject_id
        WHERE e.teacher_id=%s
        ORDER BY e.created_at DESC
    """, (request.user_id,))
    return jsonify([dict(r) for r in rows])

@exams_bp.route('/api/exams', methods=['POST'])
@require_guru
def create_exam():
    data = request.json or {}
    exam_id = str(uuid.uuid4())
    query("""INSERT INTO exams
             (id, teacher_id, subject_id, title, instructions, duration_minutes,
              start_at, status, randomize_questions, randomize_options,
              show_result_after, show_key_after, score_per_correct)
             VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s)""",
          (exam_id, request.user_id,
           data.get('subject_id') or None,
           data.get('title','Ujian Baru'),
           data.get('instructions',''),
           int(data.get('duration_minutes',90)),
           data.get('start_at'),
           data.get('randomize_questions', True),
           data.get('randomize_options', True),
           data.get('show_result_after', True),
           data.get('show_key_after', False),
           data.get('score_per_correct') or None), fetch='none')
    # Assign classes
    for cls in (data.get('class_ids') or []):
        query("INSERT INTO exam_classes (exam_id, class_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
              (exam_id, cls), fetch='none')
    return jsonify({'id': exam_id}), 201

@exams_bp.route('/api/exams/<exam_id>', methods=['GET'])
@require_auth
def get_exam(exam_id):
    exam = query("SELECT * FROM exams WHERE id=%s", (exam_id,), fetch='one')
    if not exam: return jsonify({'error': 'Tidak ditemukan'}), 404
    questions = query("SELECT * FROM questions WHERE exam_id=%s ORDER BY order_num", (exam_id,))
    q_list = []
    for q in questions:
        opts = query("SELECT * FROM options WHERE question_id=%s ORDER BY label", (q['id'],))
        q_list.append({**dict(q), 'options': [dict(o) for o in opts]})
    classes = query("""SELECT c.* FROM classes c JOIN exam_classes ec ON ec.class_id=c.id
                       WHERE ec.exam_id=%s ORDER BY c.name""", (exam_id,))
    return jsonify({**dict(exam), 'questions': q_list, 'classes': [dict(c) for c in classes]})

@exams_bp.route('/api/exams/<exam_id>', methods=['PATCH'])
@require_guru
def update_exam(exam_id):
    data = request.json or {}
    allowed = ['title','instructions','duration_minutes','start_at','status',
               'randomize_questions','randomize_options','show_result_after',
               'show_key_after','subject_id','score_per_correct']
    for f in [k for k in data if k in allowed]:
        query(f"UPDATE exams SET {f}=%s WHERE id=%s", (data[f], exam_id), fetch='none')
    if 'class_ids' in data:
        query("DELETE FROM exam_classes WHERE exam_id=%s", (exam_id,), fetch='none')
        for cls in (data['class_ids'] or []):
            query("INSERT INTO exam_classes (exam_id, class_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                  (exam_id, cls), fetch='none')
    return jsonify({'ok': True})

@exams_bp.route('/api/exams/<exam_id>', methods=['DELETE'])
@require_guru
def delete_exam(exam_id):
    query("DELETE FROM exams WHERE id=%s AND teacher_id=%s", (exam_id, request.user_id), fetch='none')
    return jsonify({'ok': True})

# ── Questions ──────────────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/questions', methods=['POST'])
@require_guru
def add_question(exam_id):
    data = request.json or {}
    q_id  = str(uuid.uuid4())
    total = query("SELECT COUNT(*) as n FROM questions WHERE exam_id=%s", (exam_id,), fetch='one')['n']
    q_type         = data.get('type', 'multiple_choice')
    attachment_url = data.get('attachment_url')
    audio_url      = data.get('audio_url')

    # Pastikan kolom type/attachment_url/audio_url ada — jalankan migration dulu jika belum
    try:
        query("""INSERT INTO questions
                   (id, exam_id, content, image_url, type, attachment_url, audio_url, order_num, score)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (q_id, exam_id, data.get('content',''), data.get('image_url'),
               q_type, attachment_url, audio_url,
               total+1, data.get('score',1)), fetch='none')
    except Exception:
        # Fallback: kolom baru belum ada, insert tanpa kolom baru
        query("""INSERT INTO questions (id, exam_id, content, image_url, order_num, score)
                 VALUES (%s,%s,%s,%s,%s,%s)""",
              (q_id, exam_id, data.get('content',''), data.get('image_url'),
               total+1, data.get('score',1)), fetch='none')

    for opt in (data.get('options') or []):
        query("INSERT INTO options (id, question_id, label, content, is_correct) VALUES (%s,%s,%s,%s,%s)",
              (str(uuid.uuid4()), q_id, opt['label'], opt['content'], opt.get('is_correct',False)), fetch='none')

    q    = query("SELECT * FROM questions WHERE id=%s", (q_id,), fetch='one')
    opts = query("SELECT * FROM options WHERE question_id=%s ORDER BY label", (q_id,))
    return jsonify({**dict(q), 'options': [dict(o) for o in opts]}), 201

@exams_bp.route('/api/questions/<question_id>', methods=['PATCH'])
@require_guru
def update_question(question_id):
    data = request.json or {}
    if 'content' in data:
        query("UPDATE questions SET content=%s WHERE id=%s", (data['content'], question_id), fetch='none')
    if 'options' in data:
        query("DELETE FROM options WHERE question_id=%s", (question_id,), fetch='none')
        for opt in data['options']:
            query("INSERT INTO options (id, question_id, label, content, is_correct) VALUES (%s,%s,%s,%s,%s)",
                  (str(uuid.uuid4()), question_id, opt['label'], opt['content'], opt.get('is_correct',False)), fetch='none')
    return jsonify({'ok': True})

@exams_bp.route('/api/questions/<question_id>', methods=['DELETE'])
@require_guru
def delete_question(question_id):
    query("DELETE FROM questions WHERE id=%s", (question_id,), fetch='none')
    return jsonify({'ok': True})

# ── Import Soal ────────────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/import', methods=['POST'])
@require_guru
def import_questions(exam_id):
    import traceback
    try:
        from openpyxl import load_workbook
        file = request.files.get('file')
        if not file: return jsonify({'error': 'File tidak ada'}), 400

        filename = file.filename or ''
        imported = 0

        # Support CSV
        if filename.lower().endswith('.csv'):
            import csv, io as _io
            content_str = file.read().decode('utf-8-sig', errors='replace')
            reader = csv.reader(_io.StringIO(content_str))
            rows = list(reader)
            data_rows = rows[1:] if rows else []  # skip header
            for i, row in enumerate(data_rows):
                if not row or not row[0].strip(): continue
                content = row[0].strip()
                options = [row[j].strip() if j < len(row) else '' for j in range(1,6)]
                correct = row[6].strip().upper() if len(row) > 6 and row[6].strip() else 'A'
                q_id = str(uuid.uuid4())
                query("INSERT INTO questions (id, exam_id, content, order_num, score) VALUES (%s,%s,%s,%s,1)",
                      (q_id, exam_id, content, i+1), fetch='none')
                for label, opt_content in zip(['A','B','C','D','E'], options):
                    if not opt_content: continue
                    query("INSERT INTO options (id, question_id, label, content, is_correct) VALUES (%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), q_id, label, opt_content, label==correct), fetch='none')
                imported += 1
        else:
            # Excel — baca ke BytesIO dulu
            import io as _io2
            file_bytes = _io2.BytesIO(file.read())
            wb = load_workbook(file_bytes)
            ws = wb.active
            for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
                if not row or not row[0]: continue
                content = str(row[0]).strip()
                options = [str(row[j] or '').strip() for j in range(1,6)]
                correct = str(row[6] or '').strip().upper() if len(row) > 6 else 'A'
                q_id = str(uuid.uuid4())
                query("INSERT INTO questions (id, exam_id, content, order_num, score) VALUES (%s,%s,%s,%s,1)",
                      (q_id, exam_id, content, i+1), fetch='none')
                for label, opt_content in zip(['A','B','C','D','E'], options):
                    if not opt_content: continue
                    query("INSERT INTO options (id, question_id, label, content, is_correct) VALUES (%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), q_id, label, opt_content, label==correct), fetch='none')
                imported += 1

        return jsonify({'ok': True, 'saved': imported, 'total': imported})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ── Monitor ────────────────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/monitor', methods=['GET'])
@require_guru
def monitor_exam(exam_id):
    exam = query("SELECT * FROM exams WHERE id=%s", (exam_id,), fetch='one')
    if not exam: return jsonify({'error': 'Tidak ditemukan'}), 404
    sessions = query("""SELECT es.*, u.name, u.avatar_url, c.name as class_name
                        FROM exam_sessions es
                        JOIN users u ON u.id=es.student_id
                        LEFT JOIN classes c ON c.id=u.class_id
                        WHERE es.exam_id=%s ORDER BY u.name""", (exam_id,))
    total_q = query("SELECT COUNT(*) as n FROM questions WHERE exam_id=%s", (exam_id,), fetch='one')['n']
    students = []
    for s in sessions:
        answered = query("SELECT COUNT(*) as n FROM answers WHERE session_id=%s AND option_id IS NOT NULL",
                         (s['id'],), fetch='one')['n']
        students.append({
            'session_id': str(s['id']),
            'student_id': str(s['student_id']),
            'name': s['name'],
            'class_name': s['class_name'],
            'status': 'submitted' if s.get('submitted_at') else 'ongoing',
            'answered': answered,
            'total': total_q,
            'tab_violations': s.get('tab_violations',0),
            'submitted_at': s['submitted_at'].isoformat() if s.get('submitted_at') else None,
            'exit_allowed': bool(s.get('exit_allowed')),
        })
    submitted = sum(1 for s in students if s['status']=='submitted')
    return jsonify({'exam': dict(exam), 'students': students,
                    'submitted': submitted, 'ongoing': len(students)-submitted})

# ── Results ────────────────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/results', methods=['GET'])
@require_guru
def exam_results(exam_id):
    rows = query("""
        SELECT u.id as student_id, u.name, u.nisn,
               c.name as class_name, es.submitted_at, es.tab_violations,
               r.score, r.correct_count, r.wrong_count, r.empty_count
        FROM exam_sessions es
        JOIN users u ON u.id=es.student_id
        LEFT JOIN classes c ON c.id=u.class_id
        LEFT JOIN results r ON r.session_id=es.id
        WHERE es.exam_id=%s ORDER BY c.name, u.name
    """, (exam_id,))
    all_rows = [dict(r) for r in rows]
    submitted = [r for r in all_rows if r.get('submitted_at')]
    scores = [float(r['score']) for r in submitted if r.get('score') is not None]
    dist = {'a':0,'b':0,'c':0,'d':0}
    for s in scores:
        if s>=90: dist['a']+=1
        elif s>=75: dist['b']+=1
        elif s>=60: dist['c']+=1
        else: dist['d']+=1
    q_stats = []
    questions = query("""
        SELECT q.id, q.content,
               COUNT(a.id) FILTER (WHERE o.is_correct=true) as correct,
               COUNT(a.id) as total
        FROM questions q
        LEFT JOIN answers a ON a.question_id=q.id AND a.session_id IN
            (SELECT id FROM exam_sessions WHERE exam_id=%s)
        LEFT JOIN options o ON o.id=a.option_id
        WHERE q.exam_id=%s GROUP BY q.id, q.content ORDER BY q.order_num
    """, (exam_id, exam_id))
    for q in questions:
        total = q['total'] or 1
        pct = round((q['correct'] or 0)/total*100, 1)
        q_stats.append({'correct': q['correct'] or 0, 'total': total, 'pct': pct})
    return jsonify({
        'results': all_rows,
        'summary': {
            'total_students': len(all_rows),
            'submitted': len(submitted),
            'avg_score': round(sum(scores)/len(scores),1) if scores else None,
            'pass_rate': round(len([s for s in scores if s>=75])/len(scores)*100,1) if scores else 0,
        },
        'score_distribution': dist,
        'question_stats': q_stats,
    })

# ── Session Detail ─────────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/student/<student_id>/detail', methods=['GET'])
@require_guru
def student_exam_detail(exam_id, student_id):
    sess = query("SELECT id FROM exam_sessions WHERE exam_id=%s AND student_id=%s LIMIT 1",
                 (exam_id, student_id), fetch='one')
    if not sess: return jsonify({'error': 'Siswa belum memulai ujian ini'}), 404
    session_id = sess['id']

    questions = query("""
        SELECT q.id, q.content, q.order_num,
               COALESCE(q.type, 'multiple_choice') as type,
               q.attachment_url, q.audio_url,
               a.option_id as student_option_id,
               ao.label as student_label, ao.content as student_answer,
               ao.is_correct as is_correct,
               co.label as correct_label, co.content as correct_answer
        FROM questions q
        LEFT JOIN answers a ON a.question_id=q.id AND a.session_id=%s
        LEFT JOIN options ao ON ao.id=a.option_id
        LEFT JOIN options co ON co.question_id=q.id AND co.is_correct=true
        WHERE q.exam_id=%s ORDER BY q.order_num, q.created_at
    """, (session_id, exam_id))

    q_list = [dict(q) for q in questions]

    # Ambil essay answers (camera_essay) dan gabungkan
    try:
        essays = query("""
            SELECT question_id, essay_text, photo_b64, teacher_score, teacher_note
            FROM essay_answers WHERE session_id=%s
        """, (session_id,))
        essay_map = {str(e['question_id']): dict(e) for e in essays}
        for q in q_list:
            if q['type'] == 'camera_essay':
                essay = essay_map.get(str(q['id']), {})
                q['essay_text']    = essay.get('essay_text', '')
                q['photo_b64']     = essay.get('photo_b64', '')
                q['teacher_score'] = essay.get('teacher_score')
                q['teacher_note']  = essay.get('teacher_note')
    except Exception:
        pass  # tabel essay_answers belum ada, tidak masalah

    # Ambil multi_answers dan gabungkan
    try:
        multis = query("""
            SELECT ma.question_id, STRING_AGG(o.label, ', ' ORDER BY o.label) as student_answer,
                   BOOL_AND(o.is_correct) as is_correct
            FROM multi_answers ma
            JOIN options o ON o.id=ma.option_id
            WHERE ma.session_id=%s
            GROUP BY ma.question_id
        """, (session_id,))
        multi_map = {str(m['question_id']): dict(m) for m in multis}
        correct_multi = query("""
            SELECT question_id, STRING_AGG(label, ', ' ORDER BY label) as correct_answer
            FROM options WHERE question_id IN (
                SELECT id FROM questions WHERE exam_id=%s AND type='multiple_answer'
            ) AND is_correct=true GROUP BY question_id
        """, (exam_id,))
        correct_multi_map = {str(r['question_id']): r['correct_answer'] for r in correct_multi}
        for q in q_list:
            if q['type'] == 'multiple_answer':
                multi = multi_map.get(str(q['id']), {})
                q['student_answer'] = multi.get('student_answer', '')
                q['is_correct']     = multi.get('is_correct', False)
                q['correct_answer'] = correct_multi_map.get(str(q['id']), '—')
    except Exception:
        pass

    return jsonify({'questions': q_list})

# ── Sessions ───────────────────────────────────────────────────
@exams_bp.route('/api/sessions/<session_id>/detail', methods=['GET'])
@require_guru
def session_detail(session_id):
    sess = query("SELECT * FROM exam_sessions WHERE id=%s", (session_id,), fetch='one')
    if not sess: return jsonify({'error': 'Tidak ditemukan'}), 404
    questions = query("""
        SELECT q.id, q.content, q.order_num, a.option_id as student_option_id,
               ao.label as student_label, ao.content as student_answer,
               ao.is_correct, co.label as correct_label, co.content as correct_answer
        FROM questions q
        LEFT JOIN answers a ON a.question_id=q.id AND a.session_id=%s
        LEFT JOIN options ao ON ao.id=a.option_id
        LEFT JOIN options co ON co.question_id=q.id AND co.is_correct=true
        WHERE q.exam_id=%s ORDER BY q.order_num
    """, (session_id, sess['exam_id']))
    result = query("SELECT * FROM results WHERE session_id=%s", (session_id,), fetch='one')
    return jsonify({'questions': [dict(q) for q in questions],
                    'result': dict(result) if result else None, 'session': dict(sess)})

# ── Finish & Publish ───────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/finish', methods=['POST'])
@require_guru
def finish_exam(exam_id):
    query("UPDATE exams SET status='finished' WHERE id=%s AND teacher_id=%s",
          (exam_id, request.user_id), fetch='none')
    return jsonify({'ok': True})

@exams_bp.route('/api/exams/<exam_id>/publish-results', methods=['POST'])
@require_guru
def publish_results(exam_id):
    query("UPDATE exams SET status='published', show_result_after=true WHERE id=%s AND teacher_id=%s",
          (exam_id, request.user_id), fetch='none')
    return jsonify({'ok': True})

# ── Export Excel ───────────────────────────────────────────────
@exams_bp.route('/api/exams/<exam_id>/export-nilai', methods=['GET'])
@require_guru
def export_nilai(exam_id):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    exam = query("SELECT * FROM exams WHERE id=%s", (exam_id,), fetch='one')
    rows = query("""
        SELECT u.name, u.nisn, c.name as class_name, es.submitted_at,
               r.score, r.correct_count, r.wrong_count, r.empty_count, es.tab_violations
        FROM exam_sessions es JOIN users u ON u.id=es.student_id
        LEFT JOIN classes c ON c.id=u.class_id
        LEFT JOIN results r ON r.session_id=es.id
        WHERE es.exam_id=%s ORDER BY c.name, u.name
    """, (exam_id,))
    wb = Workbook(); ws = wb.active; ws.title = 'Rekap Nilai'
    header_fill = PatternFill("solid", fgColor="0F4C35")
    headers = ['No','Nama','NISN','Kelas','Waktu Submit','Nilai','Benar','Salah','Kosong','Pelanggaran']
    for j, h in enumerate(headers, 1):
        cell = ws.cell(1, j, h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    for i, r in enumerate(rows, 1):
        ws.append([i, r['name'], r['nisn'], r['class_name'],
                   str(r['submitted_at'])[:16] if r['submitted_at'] else 'Belum',
                   float(r['score']) if r['score'] else 0,
                   r['correct_count'], r['wrong_count'], r['empty_count'], r['tab_violations']])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f"nilai_{exam['title'] if exam else 'ujian'}.xlsx")

# ── Template Soal ──────────────────────────────────────────────
@exams_bp.route('/api/template-soal', methods=['GET'])
@require_guru
def template_soal():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = 'Template Soal'
    ws.append(['Pertanyaan','Pilihan A','Pilihan B','Pilihan C','Pilihan D','Pilihan E','Kunci (A/B/C/D/E)'])
    ws.append(['Contoh: Ibu kota Indonesia adalah?','Jakarta','Surabaya','Bandung','Medan','','A'])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='template_soal.xlsx')
