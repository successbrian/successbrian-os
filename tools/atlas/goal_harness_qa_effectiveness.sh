#!/bin/bash
# QA probe (sbos-program-registry/effectiveness-followups-tracked):
# outcome-shaped - every harness-era completed step must carry
# an effectiveness follow-up row (the follow-up net has no
# holes), and verdicts accumulate as intervals fall due.
missing=$(psql -d ecosystem_central -Atc "select count(*) from successbrian_os.pm_steps s where s.status='done' and s.finished_at >= '2026-11-20' and (s.source like 'goal_coverage:%' or s.source like 'decomp_assist:%') and not exists (select 1 from successbrian_os.effect_followups f where f.step_id = s.id)")
total=$(psql -d ecosystem_central -Atc "select count(*) from successbrian_os.effect_followups")
verdicts=$(psql -d ecosystem_central -Atc "select count(*) from successbrian_os.effect_followups where verdict is not null")
if [ "${missing:-1}" -eq 0 ] && [ "${total:-0}" -gt 0 ]; then echo "EFFECTIVENESS-TRACKING-$total-VERDICTS-$verdicts"; exit 0; fi
echo "EFFECTIVENESS-GAPS-missing-$missing"; exit 1
