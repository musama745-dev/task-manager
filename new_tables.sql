-- Only the NEW tables for features
-- Run this in Supabase SQL Editor

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

-- RLS for new tables
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['time_entries','task_dependencies','task_templates','board_roles','undo_log','reminders']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=t AND policyname=format('anon_all_%s',t)) THEN
            EXECUTE format('CREATE POLICY "anon_all_%s" ON public.%I FOR ALL TO anon USING (true) WITH CHECK (true)',t,t);
        END IF;
    END LOOP;
END $$;
