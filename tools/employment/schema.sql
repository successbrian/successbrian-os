-- SuccessBrian OS: employment intel schema.
-- Extends public.job_tracking (existing 40-row table from the July 2026 hunt)
-- into the permanent employment stream's lead pipeline, and adds the
-- shared criteria row the scan + matcher read.
--
-- Brian 2026-10-03: "employment is a permanent stream in my ecosystem...
-- the ecosystem [should] scrape and seek out Intel regularly too and keep
-- learning and growing daily."

-- 1) Lead pipeline columns on the existing table.
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS source TEXT;
-- source: 'recruiter_email' | 'job_board_alert' | 'craigslist' | 'web_seek' | 'manual'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS source_detail TEXT;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS contact_name TEXT;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS contact_email TEXT;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS pay_range TEXT;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS remote BOOLEAN;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS employment_type TEXT;
-- employment_type: 'w2' | 'contract' | 'freelance'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS track TEXT;
-- track: 'crew2_replacement' | 'freelance_ai' | 'other'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS application_status TEXT;
-- application_status: NULL | 'lead' | 'applied' | 'interviewing' | 'offer' | 'rejected' | 'paused' | 'cold'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS next_action TEXT;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS next_action_due DATE;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS message_id_hash TEXT;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS job_tracking_message_hash_uidx
    ON public.job_tracking (message_id_hash) WHERE message_id_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS job_tracking_track_idx ON public.job_tracking (track);
CREATE INDEX IF NOT EXISTS job_tracking_status_idx2 ON public.job_tracking (application_status);

-- 2) Shared matching criteria. One row per user ('brian' today); the scan,
-- the matcher, and any agent read this instead of hardcoding his rules.
CREATE TABLE IF NOT EXISTS public.employment_criteria (
    user_id    TEXT PRIMARY KEY,
    criteria   JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.employment_criteria (user_id, criteria) VALUES (
    'brian',
    '{
        "w2_replacement": {
            "replaces": "CREW2",
            "must_be_remote": true,
            "pay_rule": "much higher than CREW2",
            "pay_floor_hourly_usd": 24,
            "target": "100k+ AI jobs",
            "schedule_constraint": "must fit around Idemia shifts (Wed/Thu 17:30-02:00, Fri 19:00-07:30, Sun 02:00-14:30 America/Chicago)"
        },
        "freelance_ai": {
            "role": "AI Applied Engineer",
            "offer": ["help companies use AI more", "improve workflows", "run AI locally"],
            "edge": "runs AI locally in production on own hardware (k11-alpha)"
        },
        "keep": ["Idemia"],
        "bulk_senders_skip": ["careerbuilder", "ziprecruiter", "nogigiddy", "directlyapply", "intuit.com", "experis"]
    }'::jsonb
) ON CONFLICT (user_id) DO UPDATE SET criteria = EXCLUDED.criteria, updated_at = now();
