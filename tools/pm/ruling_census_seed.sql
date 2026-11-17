CREATE TABLE IF NOT EXISTS successbrian_os.ruling_census (
    id serial PRIMARY KEY,
    ruling text NOT NULL,
    quote text,
    provenance text NOT NULL DEFAULT 'verbatim',
    ruled_on date,
    category text NOT NULL,
    subject text NOT NULL,
    qa_check_id integer,
    check_note text,
    status text NOT NULL DEFAULT 'live',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON successbrian_os.ruling_census TO successbrian, altair;
GRANT USAGE, SELECT ON SEQUENCE successbrian_os.ruling_census_id_seq TO successbrian, altair;
SELECT 'census table ready', count(*) FROM successbrian_os.ruling_census;
UPDATE successbrian_os.pm_project_checks SET spec = $spec${"cmd": ["bash", "-lc", "test $(psql ecosystem_central -Atc \"SELECT count(*) FROM public.gpu_price_tracker WHERE card_key IN ('v100_pcie_32','arc_b70_32','tesla_m40_24','rtx_a2000_12')\") = 4 && test $(psql ecosystem_central -Atc \"SELECT count(*) FROM atlas.scattered_captures WHERE title LIKE 'GPU price watch%' AND created_at > now() - interval '36 hours'\") -ge 1 && echo WATCH-ALIVE"], "contains": "WATCH-ALIVE"}$spec$::jsonb WHERE id = 729;
UPDATE successbrian_os.pm_project_checks SET spec = $spec${"cmd": ["bash", "-lc", "test $(psql ecosystem_central -Atc \"SELECT count(*) FROM bus.events WHERE event_type='clerk_deep_pass' AND created_at > now() - interval '7 days'\") = 0 && echo CLERK-BAN-HOLDS"], "contains": "CLERK-BAN-HOLDS"}$spec$::jsonb WHERE id = 730;
UPDATE successbrian_os.pm_project_checks SET spec = $spec${"cmd": ["bash", "-lc", "test \"$(psql ecosystem_central -Atc \"SELECT hard_terms->>'health_gate_pct' FROM dealsdesk.ecosystem_needs WHERE id=47\")\" = \"90\" && echo HEALTH-GATE-90"], "contains": "HEALTH-GATE-90"}$spec$::jsonb WHERE id = 731;
UPDATE successbrian_os.pm_project_checks SET spec = $spec${"cmd": ["bash", "-lc", "test $(psql ecosystem_central -Atc \"SELECT count(*) FROM successbrian_os.ruling_census c JOIN successbrian_os.pm_project_checks q ON q.id = c.qa_check_id WHERE q.last_run_at IS NULL OR q.last_run_at < now() - interval '48 hours'\") = 0 && echo CENSUS-CURRENT"], "contains": "CENSUS-CURRENT"}$spec$::jsonb WHERE id = 732;

INSERT INTO successbrian_os.ruling_census (ruling, quote, provenance, ruled_on, category, subject, qa_check_id, check_note, status) VALUES
($q$Track the RTX A2000 12GB — the desk watches its price$q$, $q$i said long long ago to track the a2000 --- deep dig, my sysem should be tracking it$q$, 'restated', '2026-11-17', 'tracking', 'need 48 + gpu watch card rtx_a2000_12', 727, 'Also QA 728 (sightings fresh 48h). Original ruling not on record — lost with the old price sweep; restored 2026-11-17.', 'live'),
($q$Ban RTX A1000, A400, T1000, T600, T400 from all tracking — under spec$q$, $q$we should ban those models from all tracking -- they are under spec for what we need$q$, 'verbatim', '2026-11-17', 'never', 'RTX A1000 / A400 / T1000 / T600 / T400', 725, 'Also QA 726 (scout wiring). Enforced in component_scout only — see the PicClick gap row.', 'live'),
($q$The Tesla M40 12GB is not wanted — the dual-unit buy is the 24GB PG600 only$q$, $q$we do not want Tesla M40 12 GB$q$, 'verbatim', '2026-11-16', 'never', 'Tesla M40 12GB (PG601)', 723, 'Price-guard exam case 20, inside the QA 723 selftest.', 'live'),
($q$DealsDesk watches the Tesla V100 32GB PCIe (alert line $663)$q$, $q$dealsdesk should be watching these, not muse$q$, 'restated', '2026-10-28', 'tracking', 'gpu watch card v100_pcie_32 + need 42', 729, 'Watch-cards probe: all 4 tracker rows exist and the daily watch ran within 36h.', 'live'),
($q$DealsDesk watches the Intel Arc Pro B70 32GB (alert line $1,049)$q$, $q$dealsdesk should be watching these, not muse$q$, 'restated', '2026-10-28', 'tracking', 'gpu watch card arc_b70_32 + need 43', 729, 'Same watch-cards probe as the V100 row.', 'live'),
($q$DealsDesk watches the Tesla M40 24GB (price record, no alert line)$q$, $q$dealsdesk should be watching these, not muse$q$, 'restated', '2026-10-28', 'tracking', 'gpu watch card tesla_m40_24 + need 44', 729, 'Same watch-cards probe. M40 watch added 2026-10-30.', 'live'),
($q$Watch for used 4TB Gen4 NVMe; a find requires documented health above 90%$q$, $q$we pick up outstanding deals on 4TB (>90% health) on the used market$q$, 'verbatim', '2026-11-12', 'tracking', 'need 47', 622, 'Also QA 731 (health gate still set to 90 in the need hard_terms).', 'live'),
($q$Feed seller intel into DealsDesk daily; seller names go into the one companies table$q$, $q$You can feed intel only you see daily into dealsdesk -- such as facebook marketplace -- put names/companies into our people/company database -- keep building intel on sellers$q$, 'verbatim', '2026-11-12', 'recurring', 'dealsdesk-intel-feed-daily + seller_capture', 627, 'Probe: spencer sightings fresh within 36h.', 'live'),
($q$The component scout sweeps the open ecosystem needs every 6 hours$q$, NULL, 'system-state', '2026-11-12', 'recurring', 'component_scout-6h cron', 629, 'Probe: scout sightings flowing.', 'live'),
($q$Gamma clerk verdicts get applied to captures — the sorting loop closes$q$, NULL, 'system-state', '2026-11-13', 'recurring', 'verdict_applier (alpha crontab, 30m)', 636, 'Probe fails when raw captures hold unapplied keeper verdicts older than 1h.', 'live'),
($q$Feed the gamma road first — gamma never sits idle while work it can do waits$q$, NULL, 'restated', '2026-11-10', 'recurring', 'gamma bus + queue keeper (fill to 5)', 567, 'Also QA 570 (gamma work flowing).', 'live'),
($q$Lyra watches gamma too — gamma writes into the worker heartbeat table$q$, $q$Plug Gamma into Lyra's watch too$q$, 'restated', '2026-11-12', 'recurring', 'worker_heartbeats row: gamma', 621, 'Probe: gamma heartbeat fresh within 30m. Bridge-written until NOTE-013 direct write lands.', 'live'),
($q$clerk_deep_pass stays banned until its token cap is raised and a single-capture classify completes$q$, NULL, 'system-state', '2026-11-11', 'never', 'bus event type clerk_deep_pass', 730, 'Probe: zero clerk_deep_pass events in 7 days. Retire this row when the ban is lifted by the book.', 'live'),
($q$price_reference is a corpse with no writer — pricing briefs must label it STALE and judge from fresh solds$q$, NULL, 'system-state', '2026-11-16', 'behavior', 'dealsdesk.price_reference / pricing_brief', 718, 'Probe: pricing-brief selftest. The dead table itself is acknowledged, not hidden.', 'live'),
($q$Prices go into Postgres, not AnythingLLM$q$, $q$prices go into postgresl, not anythingllm$q$, 'verbatim', '2026-11-09', 'behavior', 'price facts storage', NULL, 'No automated probe — checked by review. Articles may quote dated prices; the record lives in Postgres.', 'manual'),
($q$Nothing on gamma makes decisions — decisions refer back to alpha (Meghan/Altair)$q$, $q$nothing on gamma makes decisions$q$, 'verbatim', '2026-11-12', 'behavior', 'gamma engines and agents', NULL, 'No automated probe — a design law, checked by review.', 'manual'),
($q$The calendar carries forward — a missed item is rescheduled, never dropped$q$, $q$this needs to be how this calendar operates$q$, 'verbatim', '2026-10-27', 'behavior', 'SBOS life calendar', NULL, 'No automated probe yet — calendar machinery behavior, checked by review.', 'manual'),
($q$Standing buy rule: two Gigabyte MZ32-AR0 rev 1.x Rome boards$q$, NULL, 'system-state', '2026-10-28', 'tracking', 'MZ32-AR0 rev 1.x x2', NULL, 'GAP at census build: the desk holds need #29 for rev 3.x; no rev 1.x need or watch exists. Flagged for Brian — rev matters, not silently substituted.', 'gap'),
($q$The do-not-track ban reaches every desk pipeline$q$, $q$we should ban those models from all tracking$q$, 'verbatim', '2026-11-17', 'never', 'picclick_rack_search / cl_full_scrape', NULL, 'GAP: the ban is enforced in component_scout only; the PicClick and Craigslist pipelines do not consult check_do_not_track yet.', 'gap'),
($q$The public SBOS repo gets a daily push, scan-guarded$q$, NULL, 'restated', '2026-11-16', 'recurring', 'sbos-daily-public-push (Muse cron)', NULL, 'Push state is not probeable from alpha; the cron reports its own failures loudly. Manual row.', 'manual');
SELECT 'seeded', count(*) FROM successbrian_os.ruling_census;
UPDATE successbrian_os.pm_project_checks SET spec = $spec${"cmd": ["bash", "-lc", "test $(psql ecosystem_central -Atc \"SELECT count(*) FROM bus.events WHERE event_type='clerk_deep_pass' AND created_at > '2026-11-12'::date\") = 0 && echo CLERK-BAN-HOLDS"], "contains": "CLERK-BAN-HOLDS"}$spec$::jsonb WHERE id = 730;
UPDATE successbrian_os.ruling_census SET check_note = 'Probe: zero clerk_deep_pass events since the 2026-11-12 ban baseline (the 2026-11-10 test events that proved the handler broken predate it). Retire this row when the ban is lifted by the book.', updated_at = now() WHERE qa_check_id = 730;
UPDATE successbrian_os.pm_project_checks SET next_due_at = now() WHERE id IN (730, 732);
