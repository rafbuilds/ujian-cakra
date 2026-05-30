-- ============================================================
-- WEB UJIAN ONLINE - SMAN 1 BATANGAN
-- Schema PostgreSQL
-- Jalankan: psql -d ujian_smaba -f schema.sql
-- ============================================================

-- Ekstensi UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- MASTER DATA
-- ============================================================

-- Kelas (X IPA 1, X IPS 2, dst)
CREATE TABLE IF NOT EXISTS classes (
    id          TEXT PRIMARY KEY,           -- x_ipa_1, x_ips_2, dst
    name        TEXT NOT NULL,              -- "X IPA 1"
    grade       INT  NOT NULL,              -- 10, 11, 12
    major       TEXT NOT NULL               -- IPA, IPS, Bahasa
);

-- Pengguna (guru, siswa, admin) — login via Google OAuth
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    google_id   TEXT UNIQUE NOT NULL,       -- dari Google OAuth
    email       TEXT UNIQUE NOT NULL,       -- harus @sman1batangan.sch.id
    name        TEXT NOT NULL,
    avatar_url  TEXT,
    role        TEXT NOT NULL DEFAULT 'siswa' CHECK (role IN ('admin','guru','siswa')),
    class_id    TEXT REFERENCES classes(id),-- hanya diisi untuk siswa
    nisn        TEXT,                       -- opsional untuk siswa
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_login  TIMESTAMPTZ
);

-- Mata pelajaran
CREATE TABLE IF NOT EXISTS subjects (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    teacher_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- UJIAN
-- ============================================================

CREATE TABLE IF NOT EXISTS exams (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title               TEXT NOT NULL,
    subject_id          UUID REFERENCES subjects(id) ON DELETE SET NULL,
    teacher_id          UUID NOT NULL REFERENCES users(id),
    start_at            TIMESTAMPTZ NOT NULL,
    duration_minutes    INT  NOT NULL DEFAULT 90,
    randomize_questions BOOLEAN DEFAULT TRUE,
    randomize_options   BOOLEAN DEFAULT TRUE,
    show_result_after   BOOLEAN DEFAULT TRUE,   -- siswa lihat nilai setelah submit
    show_key_after      BOOLEAN DEFAULT FALSE,  -- siswa lihat kunci jawaban
    status              TEXT DEFAULT 'draft' CHECK (status IN ('draft','published','ongoing','finished')),
    instructions        TEXT,                   -- petunjuk ujian
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Kelas yang ikut ujian (many-to-many)
CREATE TABLE IF NOT EXISTS exam_classes (
    exam_id     UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    class_id    TEXT NOT NULL REFERENCES classes(id),
    PRIMARY KEY (exam_id, class_id)
);

-- ============================================================
-- SOAL & PILIHAN JAWABAN
-- ============================================================

CREATE TABLE IF NOT EXISTS questions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exam_id     UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,          -- teks soal
    image_url   TEXT,                   -- opsional gambar soal
    order_num   INT  NOT NULL DEFAULT 1,-- urutan soal
    score       DECIMAL DEFAULT 1,      -- bobot nilai per soal
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS options (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    label       TEXT NOT NULL,          -- A, B, C, D, E
    content     TEXT NOT NULL,          -- teks pilihan
    is_correct  BOOLEAN DEFAULT FALSE,
    UNIQUE(question_id, label)
);

-- ============================================================
-- SESI UJIAN SISWA
-- ============================================================

CREATE TABLE IF NOT EXISTS exam_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exam_id         UUID NOT NULL REFERENCES exams(id),
    student_id      UUID NOT NULL REFERENCES users(id),
    token           TEXT UNIQUE NOT NULL,   -- token akses ujian
    device_key      TEXT NOT NULL,          -- fingerprint perangkat
    ip_address      TEXT,
    tab_violations  INT  DEFAULT 0,         -- jumlah pindah tab
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    last_activity   TIMESTAMPTZ DEFAULT NOW(),
    submitted_at    TIMESTAMPTZ,            -- null = belum submit
    auto_submitted  BOOLEAN DEFAULT FALSE,  -- TRUE jika waktu habis
    UNIQUE(exam_id, student_id),            -- 1 siswa 1 sesi per ujian
    UNIQUE(exam_id, device_key)             -- 1 perangkat 1 sesi per ujian
);

-- Jawaban siswa (disimpan per soal untuk auto-save)
CREATE TABLE IF NOT EXISTS answers (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    question_id UUID NOT NULL REFERENCES questions(id),
    option_id   UUID REFERENCES options(id),    -- null = belum dijawab
    answered_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, question_id)             -- 1 jawaban per soal per sesi
);

-- ============================================================
-- HASIL & NILAI
-- ============================================================

CREATE TABLE IF NOT EXISTS results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID UNIQUE NOT NULL REFERENCES exam_sessions(id),
    student_id      UUID NOT NULL REFERENCES users(id),
    exam_id         UUID NOT NULL REFERENCES exams(id),
    score           DECIMAL NOT NULL DEFAULT 0, -- nilai 0-100
    correct_count   INT     NOT NULL DEFAULT 0,
    wrong_count     INT     NOT NULL DEFAULT 0,
    empty_count     INT     NOT NULL DEFAULT 0,
    total_questions INT     NOT NULL DEFAULT 0,
    published       BOOLEAN DEFAULT FALSE,      -- guru publish sebelum siswa lihat
    calculated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES (performa query)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_users_google_id   ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_email        ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_class        ON users(class_id);
CREATE INDEX IF NOT EXISTS idx_questions_exam     ON questions(exam_id, order_num);
CREATE INDEX IF NOT EXISTS idx_options_question   ON options(question_id);
CREATE INDEX IF NOT EXISTS idx_sessions_exam      ON exam_sessions(exam_id);
CREATE INDEX IF NOT EXISTS idx_sessions_student   ON exam_sessions(student_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token     ON exam_sessions(token);
CREATE INDEX IF NOT EXISTS idx_answers_session    ON answers(session_id);
CREATE INDEX IF NOT EXISTS idx_results_exam       ON results(exam_id);
CREATE INDEX IF NOT EXISTS idx_results_student    ON results(student_id);

-- ============================================================
-- DATA AWAL: Kelas SMAN 1 Batangan (28 kelas, 3 jurusan)
-- ============================================================

INSERT INTO classes (id, name, grade, major) VALUES
-- Kelas X
('x_ipa_1','X IPA 1',10,'IPA'), ('x_ipa_2','X IPA 2',10,'IPA'),
('x_ipa_3','X IPA 3',10,'IPA'), ('x_ipa_4','X IPA 4',10,'IPA'),
('x_ips_1','X IPS 1',10,'IPS'), ('x_ips_2','X IPS 2',10,'IPS'),
('x_ips_3','X IPS 3',10,'IPS'), ('x_ips_4','X IPS 4',10,'IPS'),
('x_bhs_1','X Bahasa 1',10,'Bahasa'),
-- Kelas XI
('xi_ipa_1','XI IPA 1',11,'IPA'), ('xi_ipa_2','XI IPA 2',11,'IPA'),
('xi_ipa_3','XI IPA 3',11,'IPA'), ('xi_ipa_4','XI IPA 4',11,'IPA'),
('xi_ips_1','XI IPS 1',11,'IPS'), ('xi_ips_2','XI IPS 2',11,'IPS'),
('xi_ips_3','XI IPS 3',11,'IPS'), ('xi_ips_4','XI IPS 4',11,'IPS'),
('xi_bhs_1','XI Bahasa 1',11,'Bahasa'),
-- Kelas XII
('xii_ipa_1','XII IPA 1',12,'IPA'), ('xii_ipa_2','XII IPA 2',12,'IPA'),
('xii_ipa_3','XII IPA 3',12,'IPA'), ('xii_ipa_4','XII IPA 4',12,'IPA'),
('xii_ips_1','XII IPS 1',12,'IPS'), ('xii_ips_2','XII IPS 2',12,'IPS'),
('xii_ips_3','XII IPS 3',12,'IPS'), ('xii_ips_4','XII IPS 4',12,'IPS'),
('xii_bhs_1','XII Bahasa 1',12,'Bahasa'),
('xii_bhs_2','XII Bahasa 2',12,'Bahasa')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- FUNCTION: hitung nilai otomatis saat submit
-- ============================================================

CREATE OR REPLACE FUNCTION calculate_result(p_session_id UUID)
RETURNS VOID AS $$
DECLARE
    v_exam_id       UUID;
    v_student_id    UUID;
    v_total         INT;
    v_correct       INT;
    v_wrong         INT;
    v_empty         INT;
    v_score         DECIMAL;
BEGIN
    SELECT exam_id, student_id INTO v_exam_id, v_student_id
    FROM exam_sessions WHERE id = p_session_id;

    SELECT COUNT(*) INTO v_total FROM questions WHERE exam_id = v_exam_id;

    SELECT COUNT(*) INTO v_correct
    FROM answers a
    JOIN options o ON a.option_id = o.id
    WHERE a.session_id = p_session_id AND o.is_correct = TRUE;

    SELECT COUNT(*) INTO v_empty
    FROM answers a
    WHERE a.session_id = p_session_id AND a.option_id IS NULL;

    v_wrong  := v_total - v_correct - v_empty;
    v_score  := CASE WHEN v_total > 0
                     THEN ROUND((v_correct::DECIMAL / v_total) * 100, 2)
                     ELSE 0 END;

    INSERT INTO results (session_id, student_id, exam_id, score,
                         correct_count, wrong_count, empty_count, total_questions)
    VALUES (p_session_id, v_student_id, v_exam_id, v_score,
            v_correct, v_wrong, v_empty, v_total)
    ON CONFLICT (session_id) DO UPDATE SET
        score           = EXCLUDED.score,
        correct_count   = EXCLUDED.correct_count,
        wrong_count     = EXCLUDED.wrong_count,
        empty_count     = EXCLUDED.empty_count,
        total_questions = EXCLUDED.total_questions,
        calculated_at   = NOW();
END;
$$ LANGUAGE plpgsql;
