-- ============================================================
-- MIGRATION: update schema ke versi terbaru
-- Jalankan SETELAH schema_ujian.sql sudah dijalankan:
--   psql -d ujian_smaba -f migration_update.sql
-- ============================================================

-- Aktifkan kedua extension UUID (uuid-ossp untuk uuid_generate_v4,
-- pgcrypto untuk gen_random_uuid — keduanya tersedia di Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── 1. Perbaiki kolom role agar menerima 'guru_pending' ──────
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin','guru','guru_pending','siswa'));

-- ── 2. Kolom tambahan di users ───────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS device_id     TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS device_info   TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS nisn          TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
-- google_id boleh NULL untuk user login manual
ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;

-- ── 3. Kolom tambahan di exams ───────────────────────────────
ALTER TABLE exams ADD COLUMN IF NOT EXISTS score_per_correct DECIMAL;
ALTER TABLE exams ADD COLUMN IF NOT EXISTS group_id    UUID;
ALTER TABLE exams ADD COLUMN IF NOT EXISTS room_id     UUID;

-- ── 4. Kolom tambahan di questions ───────────────────────────
ALTER TABLE questions ADD COLUMN IF NOT EXISTS type           TEXT DEFAULT 'multiple_choice';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS attachment_url TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS audio_url      TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS max_choices    INT; -- batas maksimal pilihan siswa untuk type='multiple_answer'

-- ── 5. Kolom tambahan di exam_sessions ───────────────────────
-- device_key boleh NULL (siswa yang belum register device)
ALTER TABLE exam_sessions ALTER COLUMN device_key DROP NOT NULL;
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS status        TEXT DEFAULT 'ongoing';
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS expires_at    TIMESTAMPTZ;
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS exit_allowed  BOOLEAN DEFAULT FALSE;

-- ── 7. Pengaturan ujian ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS exam_settings (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    passing_grade           DECIMAL DEFAULT 75,
    allow_remedial          BOOLEAN DEFAULT TRUE,
    max_violations          INT     DEFAULT 5,
    auto_submit_on_violation BOOLEAN DEFAULT TRUE,
    show_ranking            BOOLEAN DEFAULT TRUE
);
-- Buat satu baris default jika belum ada
INSERT INTO exam_settings (passing_grade, allow_remedial, max_violations, auto_submit_on_violation, show_ranking)
SELECT 75, true, 5, true, true
WHERE NOT EXISTS (SELECT 1 FROM exam_settings);

-- ── 8. Undangan guru ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS guru_invites (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL,
    name_hint   TEXT,
    token       TEXT NOT NULL UNIQUE,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    used_at     TIMESTAMPTZ,
    used_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 9. Kelas per guru ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS guru_classes (
    teacher_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    class_id   TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    PRIMARY KEY (teacher_id, class_id)
);

-- ── 10. Exam Groups ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS exam_groups (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    description TEXT,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exam_group_members (
    group_id   UUID NOT NULL REFERENCES exam_groups(id) ON DELETE CASCADE,
    teacher_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (group_id, teacher_id)
);

-- ── 11. Rooms ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rooms (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    description TEXT,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS room_teachers (
    room_id    UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    teacher_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (room_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS room_classes (
    room_id  UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    PRIMARY KEY (room_id, class_id)
);

-- ── 12. Essay & Multi-answer ──────────────────────────────────
CREATE TABLE IF NOT EXISTS essay_answers (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id   UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    question_id  UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    essay_text   TEXT,
    photo_b64    TEXT,
    score        DECIMAL,
    graded_by    UUID REFERENCES users(id),
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (session_id, question_id)
);

CREATE TABLE IF NOT EXISTS multi_answers (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_id   UUID NOT NULL REFERENCES options(id) ON DELETE CASCADE,
    answered_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 13. Media lampiran soal ───────────────────────────────────
CREATE TABLE IF NOT EXISTS exam_media (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exam_id     UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    media_type  TEXT NOT NULL DEFAULT 'attachment',
    url         TEXT NOT NULL,
    filename    TEXT,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 14. Activity Log (baru) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(64) NOT NULL,
    detail      TEXT,
    ip_address  VARCHAR(64),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user    ON activity_logs(user_id);

-- ── 15. Tahun Ajaran & Semester (baru) ───────────────────────
CREATE TABLE IF NOT EXISTS academic_years (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(20) NOT NULL UNIQUE,
    is_active  BOOLEAN DEFAULT FALSE,
    start_date DATE,
    end_date   DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS semesters (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    academic_year_id UUID NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    name             VARCHAR(20) NOT NULL,
    is_active        BOOLEAN DEFAULT FALSE,
    start_date       DATE,
    end_date         DATE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 18. Kolom teacher_note di essay_answers ─────────────────
ALTER TABLE essay_answers ADD COLUMN IF NOT EXISTS teacher_note TEXT;

-- ── 17. Kolom untuk resume session ──────────────────────────
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS paused_at    TIMESTAMPTZ;
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS extra_minutes INT DEFAULT 0;
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS reopen_count INT DEFAULT 0;

-- ── 16. Indexes tambahan ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_device      ON users(device_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status   ON exam_sessions(status) WHERE submitted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_results_session   ON results(session_id);
CREATE INDEX IF NOT EXISTS idx_guru_invites_token ON guru_invites(token);

-- ── 19. Exam Groups sebagai struktur Grup > Jenjang > Guru+Soal ──
-- Grup ujian (misal "TTS 2026/2027") murni struktur organisasi, BUKAN slot
-- jadwal bersama. Guru join sendiri ke grup, lalu saat bikin ujian pilih
-- jenjang (grade) sebagai "folder" — banyak guru boleh bikin ujian sendiri
-- untuk jenjang & mapel yang sama (kelas dibagi antar guru).
-- Catatan: exam_groups.start_at/duration_minutes (migrasi versi lama) sudah
-- tidak dipakai lagi, dibiarkan ada di DB (tidak di-drop, tidak berbahaya).
ALTER TABLE exams ADD COLUMN IF NOT EXISTS grade INT; -- 10/11/12, opsional

-- ── 20. Pengawas Universal — SATU kode global untuk semua ujian ─
-- Admin set 1 kode di exam_settings (bukan kode acak per-ujian seperti versi
-- lama — kolom exams.proctor_code dari migrasi lama sudah tidak dipakai).
-- Guru pembuat soal otomatis bisa mengawasi ujiannya sendiri tanpa kode.
-- Guru lain pilih ujian dari dropdown lalu masukkan kode global untuk bisa
-- mengawasi — akses tersimpan permanen per-ujian setelah berhasil sekali.
ALTER TABLE exam_settings ADD COLUMN IF NOT EXISTS proctor_code TEXT;
CREATE TABLE IF NOT EXISTS exam_proctors (
    exam_id    UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    teacher_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (exam_id, teacher_id)
);
CREATE INDEX IF NOT EXISTS idx_exam_proctors_teacher ON exam_proctors(teacher_id);

-- ── 21. Bank Soal — soal murni tanpa jadwal ──────────────────────
-- exams.start_at dulu NOT NULL (lihat schema_ujian.sql). Sekarang dibuat
-- nullable: ujian dengan start_at masih NULL = "Bank Soal" (belum
-- dijadwalkan/diterapkan ke kelas & room). Begitu guru pilih room+jenjang+
-- kelas+tanggal lewat "Terapkan ke Ujian", start_at terisi dan ujian itu
-- otomatis pindah tampil di Daftar Ujian / Room Ujian.
ALTER TABLE exams ALTER COLUMN start_at DROP NOT NULL;

-- ── 22. Ujian otomatis ditandai semester ─────────────────────────
-- Diutamakan ikut semester Room-nya (lihat #23). Kalau ujian tidak punya
-- room (misal soal lepas di Bank Soal), fallback ke semester yang admin
-- tandai aktif (tabel semesters.is_active) — frozen di waktu pembuatan,
-- tidak ikut berubah kalau admin ganti semester aktif belakangan.
ALTER TABLE exams ADD COLUMN IF NOT EXISTS semester_id UUID REFERENCES semesters(id) ON DELETE SET NULL;

-- ── 23. Room Ujian terikat Tahun Ajaran & Semester ────────────────
-- Admin pilih tahun ajaran+semester saat membuat/edit Room (misal
-- "TTS 2026/2027" -> Semester Genap 2026/2027). Semua ujian yang dibuat
-- guru di dalam room ini otomatis ikut semester room tersebut, sehingga
-- rekap histori per tahun ajaran/semester tetap akurat walau admin nanti
-- mengaktifkan semester yang berbeda.
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS semester_id UUID REFERENCES semesters(id) ON DELETE SET NULL;

-- ── 24. Deteksi Soal Serupa ───────────────────────────────────────
-- pg_trgm untuk fuzzy text similarity (sudah tersedia bawaan di Supabase).
-- Dipakai untuk mengingatkan guru/admin kalau pernah membuat soal dengan
-- isi yang mirip, supaya tidak dobel bikin soal yang sama.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_questions_content_trgm ON questions USING gin (content gin_trgm_ops);

-- ── 25. Pilihan jawaban bergambar ─────────────────────────────────
-- Guru minta agar Pilihan A/B/C/D/E bisa diisi gambar, tidak harus teks
-- (misal soal not musik/simbol yang sulit dideskripsikan dalam teks).
-- content dibuat nullable karena sekarang pilihan boleh isi gambar saja.
ALTER TABLE options ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE options ALTER COLUMN content DROP NOT NULL;

-- ── 26. Keluar ujian darurat — HARUS bisa dipakai walau 100% offline ──
-- HP mati/rusak total TIDAK butuh kode apa pun — siswa tinggal login ulang
-- di device lain (mis. PC lab), exam_sessions yang sama otomatis
-- dilanjutkan, tidak mulai dari awal (lihat start_exam).
--
-- Untuk kuota internet habis/offline mendadak (worst case — TIDAK BOLEH
-- butuh koneksi sama sekali saat dipakai): exit_code dibuat sekali secara
-- OTOMATIS saat siswa mulai ujian (masih online), dikirim & disimpan
-- LANGSUNG di halaman ujian siswa (di memori browser) sejak awal. Kode yang
-- sama juga otomatis tampil di tabel Monitor Siswa pengawas (tanpa perlu
-- generate manual). Saat siswa klik "Keluar Ujian", kode dicocokkan
-- SEPENUHNYA di browser (tidak perlu kirim ke server), supaya tetap bisa
-- dipakai walau sinyal sudah 100% hilang — mencegah auto-submit gara-gara
-- terhitung "pindah tab" 5x saat siswa terpaksa menyingkir dari device.
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS exit_code TEXT;
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS exited_at TIMESTAMPTZ;
-- Bersihkan sisa desain lama (kode sekali-pakai generate manual oleh guru —
-- diganti exit_code otomatis di atas) kalau migrasi versi sebelumnya sudah
-- pernah dijalankan:
DROP TABLE IF EXISTS device_transfer_codes;
ALTER TABLE users DROP COLUMN IF EXISTS unlock_code;

-- ── 27. Multi-tenant: tabel sekolah + role super_admin ────────────
-- Satu instance backend+database sekarang bisa melayani BANYAK sekolah.
-- school_id ditambahkan ke semua tabel data utama; setiap admin/guru/siswa
-- selalu terikat 1 sekolah. super_admin (pemilik platform) TIDAK terikat
-- sekolah manapun — school_id-nya NULL permanen, bisa lihat semua sekolah.
CREATE TABLE IF NOT EXISTS schools (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    slug       TEXT UNIQUE NOT NULL,
    plan       TEXT DEFAULT 'standard',
    is_active  BOOLEAN DEFAULT TRUE,   -- toggle manual super_admin (suspend akses kalau belum bayar)
    paid_until DATE,                   -- tanggal jatuh tempo pembayaran lisensi
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sekolah default untuk SEMUA data yang sudah ada (SMAN 1 Batangan) —
-- supaya migrasi ini aman dijalankan di database produksi yang sudah
-- berisi data, tanpa ada baris school_id NULL setelah migrasi selesai.
INSERT INTO schools (id, name, slug, plan, is_active)
SELECT '00000000-0000-0000-0000-000000000001', 'SMAN 1 Batangan', 'sman1batangan', 'standard', true
WHERE NOT EXISTS (SELECT 1 FROM schools WHERE slug = 'sman1batangan');

ALTER TABLE users          ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE exams          ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE rooms          ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE classes        ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE subjects       ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE academic_years ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE semesters      ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE exam_settings  ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE exam_sessions  ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE activity_logs  ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);
ALTER TABLE guru_invites   ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id);

-- Backfill semua baris yang sudah ada ke sekolah default di atas.
UPDATE users          SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE exams          SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE rooms          SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE classes        SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE subjects       SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE academic_years SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE semesters      SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE exam_settings  SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE exam_sessions  SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;
UPDATE activity_logs  SET school_id='00000000-0000-0000-0000-000000000001' WHERE school_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_school    ON users(school_id);
CREATE INDEX IF NOT EXISTS idx_exams_school    ON exams(school_id);
CREATE INDEX IF NOT EXISTS idx_rooms_school    ON rooms(school_id);
CREATE INDEX IF NOT EXISTS idx_sessions_school ON exam_sessions(school_id);

-- Role super_admin ditambahkan ke constraint yang sudah ada.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('super_admin','admin','guru','guru_pending','siswa'));

-- ── 28. academic_years.name UNIQUE global → per-sekolah ──────────
-- "2026/2027" tadinya unik secara GLOBAL (bug laten dari era single-tenant)
-- — begitu 2 sekolah pakai tahun ajaran yang namanya sama, akan bentrok.
ALTER TABLE academic_years DROP CONSTRAINT IF EXISTS academic_years_name_key;
ALTER TABLE academic_years ADD CONSTRAINT academic_years_school_name_key UNIQUE (school_id, name);

-- CATATAN PENTING: classes.id masih TEXT bebas (mis. 'x_ipa_1'), bukan
-- per-sekolah secara skema — kalau 2 sekolah punya kelas dengan id yang
-- sama persis akan bentrok primary key. Untuk sekarang dihindari lewat
-- konvensi penamaan (prefix slug sekolah) saat membuat kelas sekolah baru,
-- BUKAN lewat constraint database — perlu diperhatikan manual sampai
-- nanti diperbaiki jadi composite key (school_id, id) kalau diperlukan.

-- ── Selesai ───────────────────────────────────────────────────
-- Verifikasi: SELECT table_name FROM information_schema.tables
--             WHERE table_schema='public' ORDER BY table_name;
