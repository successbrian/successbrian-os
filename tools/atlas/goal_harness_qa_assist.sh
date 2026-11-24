#!/bin/bash
# QA probe (sbos-program-registry/breakdown-assist-reviews-moving):
# outcome-shaped - a weaker seat's draft must have been CHECKED
# (Einstein review settled into a terminal review state) in the
# last 14 days. Fails honestly until the first review lands.
n=$(psql -d ecosystem_central -Atc "select count(*) from successbrian_os.breakdown_drafts where status in ('materialized','escalated','revise-returned','draft-failed') and updated_at > now() - interval '14 days'")
total=$(psql -d ecosystem_central -Atc "select count(*) from successbrian_os.breakdown_drafts")
if [ "${n:-0}" -gt 0 ]; then echo "ASSIST-REVIEWED-$n"; exit 0; fi
if [ "${total:-0}" -gt 0 ]; then echo "ASSIST-UNREVIEWED"; exit 1; fi
echo "ASSIST-NO-DRAFTS"; exit 1
