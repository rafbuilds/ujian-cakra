# backend/routes/super_admin.py
# Dashboard pemilik platform — kelola sekolah (tenant), status pembayaran,
# dan domain email per sekolah. Endpoint ini SENGAJA tidak diturunkan dari
# require_admin (lihat auth.py require_super_admin) supaya admin sekolah
# biasa tidak pernah bisa naik privilege ke sini walau ada bug di tempat
# lain.
from flask import Blueprint, request, jsonify
import re, uuid
from db import query
from auth import require_super_admin

super_admin_bp = Blueprint('super_admin', __name__)

_SLUG_RE = re.compile(r'[^a-z0-9]+')


def _slugify(name):
    base = _SLUG_RE.sub('-', name.strip().lower()).strip('-') or 'sekolah'
    slug = base
    n = 1
    while query("SELECT 1 FROM schools WHERE slug=%s", (slug,), fetch='one'):
        n += 1
        slug = f"{base}-{n}"
    return slug


@super_admin_bp.route('/api/super-admin/overview', methods=['GET'])
@require_super_admin
def overview():
    """Ringkasan lintas-sekolah untuk kartu statistik di atas tabel —
    termasuk beban real-time (siswa yang sedang mengerjakan ujian SEKARANG,
    dipakai untuk pantau kapasitas server, bukan cuma data historis)."""
    row = query("""
        SELECT
            (SELECT COUNT(*) FROM schools) as total_schools,
            (SELECT COUNT(*) FROM schools WHERE is_active=true) as active_schools,
            (SELECT COUNT(*) FROM users WHERE role='guru') as total_guru,
            (SELECT COUNT(*) FROM users WHERE role='siswa') as total_siswa,
            (SELECT COUNT(*) FROM exams) as total_exams,
            (SELECT COUNT(*) FROM exam_sessions WHERE submitted_at IS NULL AND status='ongoing') as active_sessions
    """, fetch='one')
    return jsonify(dict(row))


@super_admin_bp.route('/api/super-admin/schools', methods=['GET'])
@require_super_admin
def list_schools():
    rows = query("""
        SELECT s.*,
               (SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role='guru') as guru_count,
               (SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role='siswa') as siswa_count,
               (SELECT COUNT(*) FROM exams e WHERE e.school_id=s.id) as exam_count
        FROM schools s
        ORDER BY s.created_at DESC
    """)
    return jsonify([dict(r) for r in rows])


@super_admin_bp.route('/api/super-admin/schools', methods=['POST'])
@require_super_admin
def create_school():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Nama sekolah wajib'}), 400
    allowed_domain = (data.get('allowed_domain') or '').strip().lower() or None
    plan = (data.get('plan') or 'standard').strip()
    paid_until = data.get('paid_until') or None
    slug = _slugify(name)
    school_id = str(uuid.uuid4())
    query("""INSERT INTO schools (id, name, slug, plan, is_active, paid_until, allowed_domain)
             VALUES (%s,%s,%s,%s,true,%s,%s)""",
          (school_id, name, slug, plan, paid_until, allowed_domain), fetch='none')
    row = query("SELECT * FROM schools WHERE id=%s", (school_id,), fetch='one')
    return jsonify(dict(row)), 201


@super_admin_bp.route('/api/super-admin/schools/<school_id>', methods=['PATCH'])
@require_super_admin
def update_school(school_id):
    data = request.json or {}
    fields, vals = [], []
    if 'name' in data:
        fields.append('name=%s'); vals.append((data['name'] or '').strip())
    if 'allowed_domain' in data:
        fields.append('allowed_domain=%s')
        vals.append((data['allowed_domain'] or '').strip().lower() or None)
    if 'plan' in data:
        fields.append('plan=%s'); vals.append((data['plan'] or 'standard').strip())
    if 'is_active' in data:
        fields.append('is_active=%s'); vals.append(bool(data['is_active']))
    if 'paid_until' in data:
        fields.append('paid_until=%s'); vals.append(data['paid_until'] or None)
    if not fields:
        return jsonify({'error': 'Tidak ada field yang valid'}), 400
    query(f"UPDATE schools SET {', '.join(fields)} WHERE id=%s", vals + [school_id], fetch='none')
    row = query("SELECT * FROM schools WHERE id=%s", (school_id,), fetch='one')
    if not row:
        return jsonify({'error': 'Sekolah tidak ditemukan'}), 404
    return jsonify(dict(row))


@super_admin_bp.route('/api/super-admin/schools/<school_id>', methods=['GET'])
@require_super_admin
def get_school(school_id):
    row = query("SELECT * FROM schools WHERE id=%s", (school_id,), fetch='one')
    if not row:
        return jsonify({'error': 'Sekolah tidak ditemukan'}), 404
    return jsonify(dict(row))
