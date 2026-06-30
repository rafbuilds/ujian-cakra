"""
storage.py — Upload gambar/audio/lampiran ke Supabase Storage, bukan
disimpan sebagai base64 langsung di kolom database.

Kenapa: base64-di-kolom-DB bikin tabel cepat membengkak (foto jawaban
siswa terutama — kelipatan jumlah siswa x soal foto x sesi ujian) dan
memperlambat semua query di tabel itu. Sekarang cuma URL publik yang
disimpan; file aslinya di object storage Supabase yang jauh lebih murah
per-GB dan tidak ikut dibaca Postgres tiap query.

Kalau SUPABASE_URL/SUPABASE_SERVICE_KEY belum di-set (mis. belum di-setup
di Render), upload_base64() fallback ke perilaku lama (simpan apa adanya)
supaya app tetap jalan, tidak crash.
"""
import os, re, uuid, base64, requests

SUPABASE_URL         = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
BUCKET               = os.environ.get('SUPABASE_STORAGE_BUCKET', 'exam-files')

_DATA_URL_RE = re.compile(r'^data:([^;]+);base64,(.+)$', re.DOTALL)


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def upload_base64(data_url, folder='misc'):
    """Upload data: URI ke Supabase Storage, kembalikan URL publiknya.
    Kalau input sudah berupa URL http(s) (sudah pernah di-upload
    sebelumnya), kembalikan apa adanya — aman dipanggil berulang di
    endpoint update tanpa re-upload tiap kali field-nya tidak berubah."""
    if not data_url:
        return data_url
    if not str(data_url).startswith('data:'):
        return data_url
    if not is_configured():
        return data_url

    m = _DATA_URL_RE.match(data_url)
    if not m:
        return data_url
    mime, b64data = m.group(1), m.group(2)
    ext = (mime.split('/')[-1].split('+')[0] or 'bin').split(';')[0]
    raw = base64.b64decode(b64data)
    path = f"{folder}/{uuid.uuid4().hex}.{ext}"

    resp = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": mime,
        },
        data=raw, timeout=20,
    )
    resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def fetch_image_bytes(value):
    """Ambil bytes gambar baik dari data: URI (lama) maupun URL Storage
    (baru) — dipakai saat embed gambar ke export Word/Excel."""
    if not value:
        return None
    v = str(value)
    try:
        if v.startswith('data:'):
            return base64.b64decode(v.split(',', 1)[1])
        if v.startswith('http://') or v.startswith('https://'):
            r = requests.get(v, timeout=20)
            r.raise_for_status()
            return r.content
        return base64.b64decode(v)  # legacy: base64 tanpa prefix data:
    except Exception:
        return None


def get_storage_usage():
    """Total ukuran semua file di bucket Storage (bytes), dihitung dengan
    menelusuri seluruh folder secara rekursif lewat Storage List API.
    None kalau Storage belum dikonfigurasi atau gagal diambil — dipakai di
    overview super_admin yang bukan rute kritis, jadi aman gagal diam-diam."""
    if not is_configured():
        return None
    try:
        total = 0
        headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
        }

        def _walk(prefix=''):
            nonlocal total
            offset = 0
            while True:
                resp = requests.post(
                    f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}",
                    headers=headers,
                    json={"prefix": prefix, "limit": 1000, "offset": offset,
                          "sortBy": {"column": "name", "order": "asc"}},
                    timeout=20,
                )
                resp.raise_for_status()
                items = resp.json()
                if not items:
                    break
                for item in items:
                    meta = item.get('metadata')
                    if meta is None:
                        # Entri tanpa metadata = folder, bukan file — telusuri isinya.
                        _walk(f"{prefix}{item['name']}/")
                    else:
                        total += meta.get('size', 0) or 0
                if len(items) < 1000:
                    break
                offset += 1000

        _walk()
        return total
    except Exception:
        return None


def is_image_ref(value):
    """True kalau value kemungkinan gambar (bukan PDF/lampiran lain)."""
    if not value:
        return False
    v = str(value)
    if v.startswith('data:image'):
        return True
    if v.startswith('http'):
        return v.lower().split('?')[0].endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
    return False
