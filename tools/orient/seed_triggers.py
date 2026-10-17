#!/usr/bin/env python3
"""Add trigger keywords to Brian's hard rules (for check_rules)."""
import sys
import os
import subprocess
sys.path.insert(0, os.path.dirname(__file__))
from orient import pg_query, lit, _pg_env


def pg_exec(sql):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(), timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"pg_exec failed: {p.stderr.strip()[:300]}")

T = "brian"

TRIGGERS = [
    ("people.people is the identity master",
     ["people.people", "systeme.io", "contact", "lead", "crm",
      "system of record", "source of truth"]),
    ("Customer tenants' data NEVER",
     ["customer", "tenant", "other user", "their data", "their leads"]),
    ("Free-first",
     ["paid", "subscription", "monthly", "api key", "saas plan", "$"]),
    ("zero chat-service dependency",
     ["hatch", "chat dependency", "manual step"]),
    ("No prices in planning talk",
     ["price", "cost", "$", "cheap", "expensive", "deal", "affordable",
      "pricey"]),
    ("Nothing destructive",
     ["delete", "drop table", "remove", "destroy", "overwrite", "truncate"]),
    ("works standalone",
     ["standalone", "dependency", "require the os", "requires os"]),
    ("future-only",
     ["reassign", "sponsor", "past", "retroactive", "rewrite history"]),
]


def main():
    pg_exec("ALTER TABLE business_core.rules "
            "ADD COLUMN IF NOT EXISTS triggers TEXT[];")
    rows = pg_query(f"SELECT id, rule FROM business_core.rules "
                    f"WHERE tenant_id={lit(T)};")
    for rid, rule in rows:
        for needle, triggers in TRIGGERS:
            if needle.lower() in rule.lower():
                arr = "ARRAY[" + ",".join(lit(t) for t in triggers) + "]"
                pg_exec(f"UPDATE business_core.rules SET triggers={arr} "
                        f"WHERE id={rid};")
                print(f"rule {rid}: {len(triggers)} triggers")
                break


if __name__ == "__main__":
    main()
