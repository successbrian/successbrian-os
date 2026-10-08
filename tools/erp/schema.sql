-- schema.sql — ERP integration tables (successbrian-os side)
-- PURPOSE: staging table for hardware needs raised by project tasks.
-- WHY: successbrian-os owns projects/tasks; DealsDesk owns ecosystem_needs.
--      This table is the deterministic handoff between them — no AI inference,
--      no hand-written bridge rows. DealsDesk's needs_intake.py promotes rows
--      here into dealsdesk.ecosystem_needs.
-- CALLED BY: DBA / Altair (one-time DDL). App code never runs DDL.
-- NOTES: run as a role with CREATE on successbrian_os (altair role if needed).

CREATE TABLE IF NOT EXISTS successbrian_os.sbos_need_requests (
    id          SERIAL PRIMARY KEY,
    task_id     BIGINT NOT NULL REFERENCES public.sbostasks(id) ON DELETE CASCADE,
    item        TEXT NOT NULL,
    specs       TEXT,
    qty         INTEGER NOT NULL DEFAULT 1,
    max_cost    NUMERIC,
    priority    INTEGER NOT NULL DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new','promoted','satisfied','dropped')),
    need_id     INTEGER REFERENCES dealsdesk.ecosystem_needs(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(task_id, item)
);

CREATE INDEX IF NOT EXISTS idx_need_requests_status
    ON successbrian_os.sbos_need_requests(status);
CREATE INDEX IF NOT EXISTS idx_need_requests_task
    ON successbrian_os.sbos_need_requests(task_id);
