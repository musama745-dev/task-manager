-- ==============================================
-- Task Manager - Supabase PostgreSQL Schema + RLS
-- Run in Supabase SQL Editor
-- ==============================================

-- ============ TABLES ============

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.boards (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    theme_color TEXT DEFAULT '#f0f2f5',
    theme_bg TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.board_lists (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

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
    assignee_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    recurring TEXT,
    next_run TIMESTAMPTZ,
    reminder_minutes INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.comments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.checklists (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    checked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.labels (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.task_labels (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    label_id INTEGER REFERENCES public.labels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.attachments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.login_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    email TEXT,
    ip TEXT,
    login_time TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.activity_log (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.board_shares (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    shared_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(board_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.time_entries (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_seconds INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.task_dependencies (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    blocked_by_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    UNIQUE(task_id, blocked_by_id)
);

CREATE TABLE IF NOT EXISTS public.task_templates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    tasks_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.board_roles (
    id SERIAL PRIMARY KEY,
    board_id INTEGER REFERENCES public.boards(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'editor',
    UNIQUE(board_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.undo_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    action_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.reminders (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES public.tasks(id) ON DELETE CASCADE,
    remind_at TIMESTAMPTZ NOT NULL,
    sent BOOLEAN DEFAULT false,
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============ ALTER COLUMNS (safe for existing DBs) ============

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS due_date TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'medium';
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS assignee_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS recurring TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS next_run TIMESTAMPTZ;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS reminder_minutes INTEGER;
ALTER TABLE public.boards ADD COLUMN IF NOT EXISTS theme_color TEXT DEFAULT '#f0f2f5';
ALTER TABLE public.boards ADD COLUMN IF NOT EXISTS theme_bg TEXT;

-- ============ ROW LEVEL SECURITY ============

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['users','boards','board_lists','tasks','checklists','labels','task_labels','attachments','login_logs','comments','activity_log','board_shares','time_entries','task_dependencies','task_templates','board_roles','undo_log','reminders']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=t AND policyname=format('anon_all_%s',t)) THEN
            EXECUTE format('CREATE POLICY "anon_all_%s" ON public.%I FOR ALL TO anon USING (true) WITH CHECK (true)',t,t);
        END IF;
    END LOOP;
END $$;

-- ============ STORAGE ============

INSERT INTO storage.buckets (id, name, public)
VALUES ('attachments', 'attachments', true)
ON CONFLICT (id) DO NOTHING;

-- ============ SEED DATA ============

INSERT INTO public.labels (name, color) SELECT 'Urgent', '#ea4335' WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name='Urgent');
INSERT INTO public.labels (name, color) SELECT 'High Priority', '#fbbc04' WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name='High Priority');
INSERT INTO public.labels (name, color) SELECT 'Medium Priority', '#1a73e8' WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name='Medium Priority');
INSERT INTO public.labels (name, color) SELECT 'Low Priority', '#34a853' WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name='Low Priority');
INSERT INTO public.labels (name, color) SELECT 'Feature', '#9c27b0' WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name='Feature');
INSERT INTO public.labels (name, color) SELECT 'Bug', '#ff6d00' WHERE NOT EXISTS (SELECT 1 FROM public.labels WHERE name='Bug');

INSERT INTO public.users (username, password, role)
SELECT 'admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM public.users WHERE username='admin');
