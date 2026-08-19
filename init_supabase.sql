-- ==============================================
-- Task Manager - Supabase PostgreSQL Schema + RLS
-- Copy & paste this into Supabase SQL Editor
-- ==============================================

-- Users
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add email column to existing users table (for already-initialized databases)
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS email TEXT;

-- Boards
CREATE TABLE IF NOT EXISTS public.boards (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Board Lists
CREATE TABLE IF NOT EXISTS public.board_lists (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tasks
CREATE TABLE IF NOT EXISTS public.tasks (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    list_id INTEGER REFERENCES public.board_lists(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending',
    due_date TEXT,
    priority TEXT DEFAULT 'medium',
    position INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add new columns to existing tasks table (for already-initialized databases)
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS due_date TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'medium';
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS assignee_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL;

-- Comments on tasks
CREATE TABLE IF NOT EXISTS public.comments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Checklists (sub-tasks)
CREATE TABLE IF NOT EXISTS public.checklists (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    checked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Labels
CREATE TABLE IF NOT EXISTS public.labels (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Task <-> Label mapping
CREATE TABLE IF NOT EXISTS public.task_labels (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    label_id INTEGER REFERENCES public.labels(id) ON DELETE CASCADE
);

-- Attachments
CREATE TABLE IF NOT EXISTS public.attachments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Login activity log
CREATE TABLE IF NOT EXISTS public.login_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    email TEXT,
    ip TEXT,
    login_time TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================
-- ROW LEVEL SECURITY
-- App khud auth karti hai (Flask + SHA256), isliye
-- anon key ko full access allowed hai.
-- ==============================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.boards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.board_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checklists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.task_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.login_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.board_shares ENABLE ROW LEVEL SECURITY;

-- Activity log for boards
CREATE TABLE IF NOT EXISTS public.activity_log (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Board sharing
CREATE TABLE IF NOT EXISTS public.board_shares (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    shared_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(board_id, user_id)
);

-- Recurring tasks support
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS recurring TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS next_run TIMESTAMPTZ;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['users','boards','board_lists','tasks','checklists','labels','task_labels','attachments','login_logs','comments','activity_log','board_shares']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t AND policyname = format('anon_all_%s', t)) THEN
            EXECUTE format('CREATE POLICY "anon_all_%s" ON public.%I FOR ALL TO anon USING (true) WITH CHECK (true)', t, t);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t AND policyname = format('anon_select_%s', t)) THEN
            EXECUTE format('CREATE POLICY "anon_select_%s" ON public.%I FOR SELECT TO anon USING (true)', t, t);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t AND policyname = format('anon_insert_%s', t)) THEN
            EXECUTE format('CREATE POLICY "anon_insert_%s" ON public.%I FOR INSERT TO anon WITH CHECK (true)', t, t);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t AND policyname = format('anon_update_%s', t)) THEN
            EXECUTE format('CREATE POLICY "anon_update_%s" ON public.%I FOR UPDATE TO anon USING (true) WITH CHECK (true)', t, t);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t AND policyname = format('anon_delete_%s', t)) THEN
            EXECUTE format('CREATE POLICY "anon_delete_%s" ON public.%I FOR DELETE TO anon USING (true)', t, t);
        END IF;
    END LOOP;
END $$;

-- ==============================================
-- STORAGE: attachments bucket
-- ==============================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('attachments', 'attachments', true)
ON CONFLICT (id) DO NOTHING;

-- ==============================================
-- Seed default labels
-- ==============================================
INSERT INTO public.labels (name, color)
SELECT 'Urgent', '#ea4335'
WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name = 'Urgent');

INSERT INTO public.labels (name, color)
SELECT 'High Priority', '#fbbc04'
WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name = 'High Priority');

INSERT INTO public.labels (name, color)
SELECT 'Medium Priority', '#1a73e8'
WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name = 'Medium Priority');

INSERT INTO public.labels (name, color)
SELECT 'Low Priority', '#34a853'
WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name = 'Low Priority');

INSERT INTO public.labels (name, color)
SELECT 'Feature', '#9c27b0'
WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name = 'Feature');

INSERT INTO public.labels (name, color)
SELECT 'Bug', '#ff6d00'
WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name = 'Bug');

-- ==============================================
-- Seed default admin (password: admin123)
-- ==============================================
INSERT INTO public.users (username, password, role)
SELECT 'admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM public.users WHERE username = 'admin');
