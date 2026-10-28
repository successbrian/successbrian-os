-- Operator health log (Brian's directive, 2026-10-28: health tracking in
-- SuccessBrian OS — sleep better, eat better, continue the road to better
-- health). State home per R32: PostgreSQL, schema successbrian_os.
-- Frame (Brian 2026-10-28 18:56 CDT): Brian's LIFE pillars are his own F
-- set — family, faith, fitness, finance (list left open by him). This log
-- is the FITNESS pillar's data home. Its sub-domains are the five health
-- pillars (standard life-coaching set, Brian 2026-10-28 18:55 CDT;
-- Brian-correctable): sleep, nutrition, movement, stress_mindset,
-- social_connection. A1C + weight ride the metabolic thread crossing
-- nutrition + movement.
-- Readings only: Brian-reported or device-synced. No targets, no advice.

CREATE TABLE IF NOT EXISTS successbrian_os.health_log (
    id            serial PRIMARY KEY,
    metric        text NOT NULL,        -- a1c / weight_lb / weight_change_lb / sleep_hours / meal_note / other
    pillar        text,                 -- sleep / nutrition / movement / stress_mindset / social_connection / nutrition+movement (metabolic)
    value         numeric,              -- NULL for note-only entries (e.g. meal_note)
    unit          text,                 -- % / lb / hours
    reading_date  date,                 -- when the reading is OF; NULL when Brian did not specify
    reported_date date NOT NULL DEFAULT CURRENT_DATE,
    source        text NOT NULL,        -- brian_chat / brian_post / device:<name>
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS health_log_metric_idx
    ON successbrian_os.health_log (metric, reading_date);
