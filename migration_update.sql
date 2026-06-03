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
ALTER TABLE users ADD COLUMN IF NOT EXISTS device_id   TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS device_info TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS nisn        TEXT;

-- ── 3. Kolom tambahan di exams ───────────────────────────────
ALTER TABLE exams ADD COLUMN IF NOT EXISTS score_per_correct DECIMAL;
ALTER TABLE exams ADD COLUMN IF NOT EXISTS group_id    UUID;
ALTER TABLE exams ADD COLUMN IF NOT EXISTS room_id     UUID;

-- ── 4. Kolom tambahan di questions ───────────────────────────
ALTER TABLE questions ADD COLUMN IF NOT EXISTS type           TEXT DEFAULT 'multiple_choice';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS attachment_url TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS audio_url      TEXT;

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

-- ── 16. Indexes tambahan ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_device      ON users(device_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status   ON exam_sessions(status) WHERE submitted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_results_session   ON results(session_id);
CREATE INDEX IF NOT EXISTS idx_guru_invites_token ON guru_invites(token);

-- ── Selesai ───────────────────────────────────────────────────
-- Verifikasi: SELECT table_name FROM information_schema.tables
--             WHERE table_schema='public' ORDER BY table_name;
