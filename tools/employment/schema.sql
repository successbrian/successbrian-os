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

-- 2026-10-04 (learnings from the Project Blue Indeed match): normalized
-- pay numbers so rows compare against the floor/target without human math;
-- tiered verdict instead of a binary worth-eyes call; masked-employer and
-- profile-staleness flags; gaps checklist of what the posting didn't say.
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS pay_hourly_low NUMERIC;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS pay_hourly_high NUMERIC;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS pay_annual_low NUMERIC;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS pay_annual_high NUMERIC;
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS ai_role BOOLEAN;
-- company_confidence: 'parsed' | 'masked' (staffing placeholder) | 'none'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS company_confidence TEXT;
-- profile_flags: comma-joined, e.g. 'profile_stale,no_min_pay'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS profile_flags TEXT;
-- gaps: comma-joined checklist of unknowns, e.g.
-- 'company_unknown,pay_unknown,hours_unknown,idemia_fit_unconfirmed'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS gaps TEXT;
-- verdict: 'target' | 'fallback' | 'below_bar'
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS verdict TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS job_tracking_message_hash_uidx
    ON public.job_tracking (message_id_hash) WHERE message_id_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS job_tracking_track_idx ON public.job_tracking (track);
CREATE INDEX IF NOT EXISTS job_tracking_status_idx2 ON public.job_tracking (application_status);
CREATE INDEX IF NOT EXISTS job_tracking_verdict_idx ON public.job_tracking (verdict);

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
            "ai_target_annual_usd": 100000,
            "crew2_pay_hourly_usd": null,
            "target": "100k+ AI jobs",
            "schedule_constraint": "must fit around Idemia shifts (Wed/Thu 17:30-02:00, Fri 19:00-07:30, Sun 02:00-14:30 America/Chicago)"
        },
        "freelance_ai": {
            "role": "AI Applied Engineer",
            "offer": ["help companies use AI more", "improve workflows", "run AI locally"],
            "edge": "runs AI locally in production on own hardware (k11-alpha)",
            "coding_profile": "Vibe coder: architects and directs AI-assisted development; builds new systems and improves workflows through AI. NOT traditionally strong hand-writing Python/JS. Best gigs: greenfield AI builds, workflow automation, local AI deployment. Weaker fit: hands-on production-code surgery in someone else's stack."
        },
        "skills": {
            "_note": "Brian's self-assessed levels (per Brian 2026-10-04): strong | developing | weak. The scout grades fit against these; the coach tracks how often leads ask for more than he has.",
            "python": "developing",
            "javascript": "developing",
            "typescript": "weak",
            "react": "weak",
            "node.js": "developing",
            "sql": "developing",
            "data_pipelines": "strong",
            "llm_apis": "strong",
            "ml_fundamentals": "developing",
            "local_llm_deploy": "strong",
            "workflow_automation": "strong",
            "docker_k8s": "developing",
            "aws_cloud": "developing",
            "trading_domain": "developing",
            "crm_tools": "developing",
            "spreadsheets": "developing"
        },
        "fit_rules": {
            "freelance_ai": "Grade coding_fit per lead: 'vibe_fit' for greenfield builds, workflow automation, local AI deploys, consulting/audits; 'hand_code_heavy' when the posting demands strong hand-written Python/JS or production-codebase surgery. Brian is a developing vibe coder — hand_code_heavy leads are stretch, not target, even when pay fits. Record required_skills and skill_gaps honestly.",
            "w2_replacement": "Same coding_fit grading applies when the role is technical; most CSR/ops roles are not code-heavy and skip it."
        },
        "keep": ["Idemia"],
        "bulk_senders_skip": ["careerbuilder", "ziprecruiter", "nogigiddy", "directlyapply", "intuit.com", "experis"]
    }'::jsonb
) ON CONFLICT (user_id) DO UPDATE SET criteria = EXCLUDED.criteria, updated_at = now();

-- 3) Skill-gap tracking (Brian 2026-10-04): the scout grades fit knowing
-- he is a DEVELOPING VIBE CODER, not a strong natural programmer — and it
-- records how often required skills he is underqualified for show up in
-- intel, so the coach can guide his learning toward what the market wants.
--
-- Per-lead columns:
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS skill_gaps JSONB;
-- skill_gaps: JSONB array of {"skill","required_level","gap_kind"}.
-- gap_kind: 'underqualified' (his level is developing/weak and the lead
-- wants more) | 'unassessed' (his level unknown + the lead wants a high
-- level). NULL = not graded yet; '[]' = graded, no gaps.
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS required_skills JSONB;
-- required_skills: JSONB array of {"skill","required_level"} — every
-- lexicon skill the posting asked for, whether or not it is a gap.
-- coding_fit: how the work itself fits a vibe coder.
-- 'vibe_fit' (greenfield builds, workflow automation, local AI deploys,
--  consulting/audits) | 'hand_code_heavy' (strong hand-written code in
--  someone else's production codebase) | 'mixed' | NULL (not graded).
ALTER TABLE public.job_tracking ADD COLUMN IF NOT EXISTS coding_fit TEXT;

-- Normalized per-lead-per-skill signals: the rollup source. One row per
-- lead per skill (a lead counts once per skill no matter how many times
-- the posting mentions it).
CREATE TABLE IF NOT EXISTS public.skill_gap_signals (
    id              SERIAL PRIMARY KEY,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    job_tracking_id INTEGER NOT NULL REFERENCES public.job_tracking(id)
                        ON DELETE CASCADE,
    skill           TEXT NOT NULL,
    required_level  TEXT,
    -- required_level: 'high' (strong/expert/senior/5+ yrs language) |
    -- 'stated' (mentioned without a level).
    gap_kind        TEXT NOT NULL,
    -- gap_kind: 'underqualified' | 'unassessed'
    track           TEXT,
    source          TEXT,
    UNIQUE (job_tracking_id, skill)
);
CREATE INDEX IF NOT EXISTS skill_gap_signals_skill_idx
    ON public.skill_gap_signals (skill, observed_at);
CREATE INDEX IF NOT EXISTS skill_gap_signals_track_idx
    ON public.skill_gap_signals (track);

-- Brian's self-assessed skill levels. The lexicon points at postings;
-- this table says where HE stands. Levels: 'strong' | 'developing' |
-- 'weak'. Update conversationally as he learns (he asked 2026-10-04 for
-- the coach to track this and guide him).
CREATE TABLE IF NOT EXISTS public.skill_lexicon (
    skill        TEXT PRIMARY KEY,
    -- skill: normalized name, e.g. 'python', 'react', 'kubernetes'.
    patterns     TEXT[] NOT NULL DEFAULT '{}',
    -- patterns: regexes (case-insensitive) matched against
    -- title || notes || pay_range.
    category     TEXT,
    brian_level  TEXT NOT NULL DEFAULT 'developing',
    notes        TEXT
);

INSERT INTO public.skill_lexicon (skill, patterns, category, brian_level, notes) VALUES
    ('python',            '{\\bpython\\b,\\bpy\\b}',            'language', 'developing', 'Vibe-codes Python daily; does not hand-write fluently (per Brian 2026-10-04).'),
    ('javascript',        '{\\bjavascript\\b,\\becmascript\\b}', 'language', 'developing', 'Same as Python: vibe-coded, not hand-fluent.'),
    ('typescript',        '{\\btypescript\\b,\\bts\\b}',        'language', 'weak',       NULL),
    ('react',             '{\\breact\\b,\\bnext\\.?js\\b}',     'framework','weak',       NULL),
    ('node.js',           '{\\bnode\\.?js\\b,\\bexpress\\b}',    'runtime',  'developing', NULL),
    ('sql',               '{\\bsql\\b,\\bpostgres\\b,\\bmysql\\b}', 'data',  'developing', 'Writes basic queries; leans on AI for complex ones.'),
    ('data_pipelines',    '{\\bdata pipeline\\b,\\betl\\b,\\bairflow\\b}', 'data', 'strong', 'His ecosystem is deterministic pipelines.'),
    ('llm_apis',          '{\\bopenai api\\b,\\bllm api\\b,\\bprompt engineering\\b,\\brag\\b}', 'ai', 'strong', 'Builds with LLM APIs constantly.'),
    ('ml_fundamentals',   '{\\bmachine learning\\b,\\bdeep learning\\b,\\bpytorch\\b,\\btensorflow\\b}', 'ai', 'developing', 'Uses models; QLoRA training planned, not done.'),
    ('local_llm_deploy',  '{\\blocal llm\\b,\\bollama\\b,\\bvllm\\b,\\bllama\\.cpp\\b,\\bon-prem.*ai\\b}', 'ai', 'strong', 'Runs models locally on k11-alpha in production.'),
    ('workflow_automation', '{\\bworkflow automation\\b,\\bn8n\\b,\\bzapier\\b,\\bmake\\.com\\b}', 'automation', 'strong', 'Automates his own business workflows.'),
    ('docker_k8s',        '{\\bdocker\\b,\\bkubernetes\\b,\\bk8s\\b}', 'infra', 'developing', 'Runs containers on k11; not a k8s operator.'),
    ('aws_cloud',         '{\\baws\\b,\\bazure\\b,\\bgcp\\b,\\bgoogle cloud\\b}', 'infra', 'developing', 'Homelab-first; cloud is not his home turf.'),
    ('trading_domain',    '{\\btrading\\b,\\bfintech\\b,\\bquant\\b,\\bforex\\b}', 'domain', 'developing', 'Trades crypto, runs a webinar; not professional fintech.'),
    ('crm_tools',         '{\\bsalesforce\\b,\\bhubspot\\b,\\bcrm\\b}', 'tools', 'developing', NULL),
    ('spreadsheets',      '{\\bexcel\\b,\\bgoogle sheets\\b}',  'tools',    'developing', NULL)
ON CONFLICT (skill) DO UPDATE SET patterns = EXCLUDED.patterns,
    category = EXCLUDED.category, brian_level = EXCLUDED.brian_level,
    notes = EXCLUDED.notes;

-- 30-day rollup the coach reads: how often each underqualified-for skill
-- showed up in recent intel, by track.
CREATE OR REPLACE VIEW public.skill_gap_rollup_30d AS
SELECT skill,
       gap_kind,
       COUNT(*) AS lead_count,
       COUNT(*) FILTER (WHERE track = 'freelance_ai') AS freelance_leads,
       COUNT(*) FILTER (WHERE track = 'crew2_replacement') AS w2_leads,
       MAX(required_level) FILTER (WHERE required_level = 'high') AS asked_high,
       MAX(observed_at) AS last_seen
FROM public.skill_gap_signals
WHERE observed_at > now() - interval '30 days'
GROUP BY skill, gap_kind
ORDER BY lead_count DESC;
