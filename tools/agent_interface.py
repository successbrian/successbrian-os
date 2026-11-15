#!/usr/bin/env python3
"""agent_interface.py — AGENT INTERFACE v1 (Phase 1): registration +
permission record for OUTSIDE agents in SuccessBrian OS.

Brian's ruling, 2026-11-15 08:32 CST: "Rule it — and start building v1"
— the v1→v2→v3 agent-interface path (plan:
~/workspace/builds/sbos-agent-interface/PLAN-2026-11-15.md on the
operator side; packet: docs/agent-interface/ARRIVAL_PACKET.md).

This module is the ONE interface to the outside-agent permission record
(written once, sbos_common spirit). It is deliberately vendor-neutral:
vendor is a name-tag field, never a separate door. An outside agent
(Muse, Grok bot, or any other) registers under its owner's operator
key, is granted a tier, and is issued a scoped token.

SAFETY MODEL (ruled, do not weaken):
  * Tokens are stored HASHED ONLY (SHA-256). The plaintext token is
    printed exactly once, at issue time. Nobody can read it back.
  * Tiers: read < propose < act. A door checks the tier it needs; a
    lower-tier agent is refused and the refusal is audited.
  * Tokens expire and are revocable; a revoked agent is refused whole.
  * There is NO send / buy / publish / contact verb in this module and
    there never will be: outward acts go through a durable pending
    approval the owner approves in SBOS (later phase).
  * Every registration / token / tier event lands in the APPEND-ONLY
    audit table with the agent's name tag.
  * Additive only: this module never touches Agent Commons tables or
    behavior (tools/agent_board.py is the Commons interface).

Tables (DDL: tools/agent_interface.sql):
  successbrian_os.agent_interface_agents — the permission record
  successbrian_os.agent_interface_audit  — append-only event audit

Usage (CLI):
  python3 agent_interface.py register-agent --operator OP --agent KEY \
      --name "Display Name" [--vendor muse] [--tier read|propose|act]
  python3 agent_interface.py issue-token --agent KEY [--days 30]
      (prints the plaintext token ONCE; only its hash is stored)
  python3 agent_interface.py verify-token --agent KEY --token T
  python3 agent_interface.py gate --agent KEY --token T \
      --need read|propose|act   (verify + tier check in one call)
  python3 agent_interface.py revoke-token --agent KEY
  python3 agent_interface.py show-agent --agent KEY [--json]
  python3 agent_interface.py selftest

Exit codes: 0 ok; 1 refused (bad/expired/revoked token, tier too low,
agent revoked, not found); 2 usage or store errors.
"""
import argparse
import hashlib
import json
import secrets
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

TIERS = ("read", "propose", "act")
TEST_OPERATOR = "selftest-operator"
TEST_AGENT = "selftest-outside-agent"
TEST_AGENT2 = "selftest-outside-agent-2"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _audit(agent_key, operator_key, event, detail=None):
    pg_exec(
        "insert into successbrian_os.agent_interface_audit "
        "(agent_key, operator_key, event, detail) values (%s,%s,%s,%s)",
        (agent_key, operator_key, event, Json(detail or {})))


def register_agent(operator_key, agent_key, display_name, vendor="other",
                   tier="read"):
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    pg_exec(
        """insert into successbrian_os.agent_interface_agents
             (agent_key, operator_key, display_name, vendor, tier)
           values (%s,%s,%s,%s,%s)
           on conflict (agent_key) do update
             set operator_key=excluded.operator_key,
                 display_name=excluded.display_name,
                 vendor=excluded.vendor,
                 tier=excluded.tier,
                 updated_at=now()""",
        (agent_key, operator_key, display_name, vendor, tier))
    _audit(agent_key, operator_key, "registered",
           {"vendor": vendor, "tier": tier})
    return show_agent(agent_key)


def issue_token(agent_key, days=30):
    row = pg_one(
        "select operator_key, agent_revoked from "
        "successbrian_os.agent_interface_agents where agent_key=%s",
        (agent_key,))
    if row is None:
        return None
    operator_key, agent_revoked = row
    if agent_revoked:
        return None
    token = "sbos_" + secrets.token_urlsafe(32)
    pg_exec(
        """update successbrian_os.agent_interface_agents
              set token_hash=%s, token_issued_at=now(),
                  token_expires_at=now() + (%s || ' days')::interval,
                  token_revoked=false, updated_at=now()
            where agent_key=%s""",
        (_hash(token), str(days), agent_key))
    _audit(agent_key, operator_key, "token_issued", {"days": days})
    return token


def _refuse(agent_key, operator_key, reason):
    _audit(agent_key, operator_key, "token_refused", {"reason": reason})
    return None


def verify_token(agent_key, token):
    """Return the agent row (dict) if the token is valid, else None.
    Every refusal is audited with its reason."""
    row = pg_one(
        """select agent_key, operator_key, display_name, vendor, tier,
                  agent_revoked, token_hash, token_revoked,
                  (token_expires_at is not null
                   and token_expires_at < now()) as token_expired
             from successbrian_os.agent_interface_agents
            where agent_key=%s""",
        (agent_key,))
    if row is None:
        return _refuse(agent_key, None, "unknown_agent")
    (key, operator_key, name, vendor, tier, agent_revoked, token_hash,
     token_revoked, token_expired) = row
    if agent_revoked:
        return _refuse(key, operator_key, "agent_revoked")
    if not token_hash:
        return _refuse(key, operator_key, "no_token_issued")
    if token_revoked:
        return _refuse(key, operator_key, "token_revoked")
    if token_expired:
        return _refuse(key, operator_key, "token_expired")
    if not secrets.compare_digest(_hash(token), token_hash):
        return _refuse(key, operator_key, "token_mismatch")
    _audit(key, operator_key, "token_verified", {"tier": tier})
    return {"agent_key": key, "operator_key": operator_key,
            "display_name": name, "vendor": vendor, "tier": tier}


def require_tier(agent: dict, need: str) -> bool:
    """Tier gate: True if the verified agent's tier covers `need`.
    A refusal is audited as tier_refused."""
    if need not in TIERS:
        raise ValueError(f"need must be one of {TIERS}")
    if TIERS.index(agent["tier"]) >= TIERS.index(need):
        return True
    _audit(agent["agent_key"], agent["operator_key"], "tier_refused",
           {"tier": agent["tier"], "need": need})
    return False


def revoke_token(agent_key):
    operator_key = pg_one(
        "select operator_key from successbrian_os.agent_interface_agents "
        "where agent_key=%s", (agent_key,))
    if operator_key is None:
        return False
    pg_exec(
        """update successbrian_os.agent_interface_agents
              set token_revoked=true, updated_at=now()
            where agent_key=%s""", (agent_key,))
    _audit(agent_key, operator_key, "token_revoked", {})
    return True


def show_agent(agent_key):
    row = pg_one(
        """select agent_key, operator_key, display_name, vendor, tier,
                  agent_revoked, token_revoked,
                  token_issued_at::text, token_expires_at::text,
                  (token_hash is not null) as has_token, created_at::text
             from successbrian_os.agent_interface_agents
            where agent_key=%s""", (agent_key,))
    if row is None:
        return None
    keys = ("agent_key", "operator_key", "display_name", "vendor", "tier",
            "agent_revoked", "token_revoked", "token_issued_at",
            "token_expires_at", "has_token", "created_at")
    return dict(zip(keys, row))


def _cleanup_test_rows():
    # Disposable selftest cleanup (the standing Commons precedent):
    # production audit rows are never deleted; selftest rows are proof
    # scaffolding and are removed whole so the record stays clean.
    pg_exec("delete from successbrian_os.agent_interface_audit "
            "where operator_key=%s", (TEST_OPERATOR,))
    pg_exec("delete from successbrian_os.agent_interface_agents "
            "where operator_key=%s", (TEST_OPERATOR,))


def selftest():
    steps = []

    def check(label, cond):
        steps.append((label, bool(cond)))
        print(f"  [{'ok' if cond else 'FAIL'}] {label}")
        if not cond:
            raise AssertionError(label)

    _cleanup_test_rows()
    print("agent_interface selftest")
    # 1. register a read-tier outside agent
    a = register_agent(TEST_OPERATOR, TEST_AGENT, "Selftest Agent",
                       vendor="selftest-vendor", tier="read")
    check("register read-tier agent", a and a["tier"] == "read")
    # 2. issue a token; only its hash is stored
    token = issue_token(TEST_AGENT, days=30)
    check("issue token returns plaintext once", bool(token))
    stored = pg_one(
        "select token_hash from successbrian_os.agent_interface_agents "
        "where agent_key=%s", (TEST_AGENT,))
    check("stored value is the hash, never the plaintext",
          stored == _hash(token) and stored != token)
    # 3. verify ok
    v = verify_token(TEST_AGENT, token)
    check("verify ok with the right token", v and v["agent_key"] == TEST_AGENT)
    # 4. wrong token refused
    check("wrong token refused",
          verify_token(TEST_AGENT, "sbos_wrong-token-value") is None)
    # 5. tier enforcement: read-tier cannot take a propose step
    check("tier gate: read-tier agent refused a propose step",
          require_tier(v, "propose") is False)
    check("tier gate: read-tier agent passes a read step",
          require_tier(v, "read") is True)
    # 6. a propose-tier agent passes the propose gate
    register_agent(TEST_OPERATOR, TEST_AGENT2, "Selftest Agent 2",
                   vendor="selftest-vendor", tier="propose")
    token2 = issue_token(TEST_AGENT2, days=30)
    v2 = verify_token(TEST_AGENT2, token2)
    check("tier gate: propose-tier agent passes a propose step",
          v2 is not None and require_tier(v2, "propose") is True)
    check("tier gate: propose-tier agent refused an act step",
          require_tier(v2, "act") is False)
    # 7. expired token refused
    pg_exec("update successbrian_os.agent_interface_agents "
            "set token_expires_at=now() - interval '1 minute' "
            "where agent_key=%s", (TEST_AGENT2,))
    check("expired token refused", verify_token(TEST_AGENT2, token2) is None)
    # 8. revoked token refused
    revoke_token(TEST_AGENT)
    check("revoked token refused", verify_token(TEST_AGENT, token) is None)
    # 9. audit rows were written for the lifecycle
    events = [r[0] for r in pg_rows(
        "select event from successbrian_os.agent_interface_audit "
        "where operator_key=%s", (TEST_OPERATOR,))]
    for expected in ("registered", "token_issued", "token_verified",
                     "token_refused", "tier_refused", "token_revoked"):
        check(f"audit contains '{expected}'", expected in events)
    _cleanup_test_rows()
    left = pg_one("select count(*) from successbrian_os.agent_interface_agents "
                  "where operator_key=%s", (TEST_OPERATOR,))
    check("cleanup: no selftest rows remain", left == 0)
    print("SELFTEST PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="SBOS Agent Interface v1 — outside-agent registration "
                    "+ permission record")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register-agent")
    r.add_argument("--operator", required=True)
    r.add_argument("--agent", required=True)
    r.add_argument("--name", required=True)
    r.add_argument("--vendor", default="other")
    r.add_argument("--tier", default="read", choices=TIERS)

    i = sub.add_parser("issue-token")
    i.add_argument("--agent", required=True)
    i.add_argument("--days", type=int, default=30)

    v = sub.add_parser("verify-token")
    v.add_argument("--agent", required=True)
    v.add_argument("--token", required=True)

    g = sub.add_parser("gate")
    g.add_argument("--agent", required=True)
    g.add_argument("--token", required=True)
    g.add_argument("--need", required=True, choices=TIERS)

    rv = sub.add_parser("revoke-token")
    rv.add_argument("--agent", required=True)

    s = sub.add_parser("show-agent")
    s.add_argument("--agent", required=True)
    s.add_argument("--json", action="store_true")

    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "selftest":
            return selftest()
        if args.cmd == "register-agent":
            a = register_agent(args.operator, args.agent, args.name,
                               args.vendor, args.tier)
            print(json.dumps(a, indent=2, default=str))
            return 0
        if args.cmd == "issue-token":
            token = issue_token(args.agent, args.days)
            if token is None:
                print("refused: unknown or revoked agent", file=sys.stderr)
                return 1
            print(token)
            print("STORE THIS NOW — it is shown once; only its hash is "
                  "kept.", file=sys.stderr)
            return 0
        if args.cmd == "verify-token":
            a = verify_token(args.agent, args.token)
            if a is None:
                print("refused", file=sys.stderr)
                return 1
            print(json.dumps(a, indent=2, default=str))
            return 0
        if args.cmd == "gate":
            a = verify_token(args.agent, args.token)
            if a is None:
                print("refused: token", file=sys.stderr)
                return 1
            if not require_tier(a, args.need):
                print(f"refused: tier {a['tier']} < {args.need}",
                      file=sys.stderr)
                return 1
            print(f"ok: {a['agent_key']} tier={a['tier']} need={args.need}")
            return 0
        if args.cmd == "revoke-token":
            if not revoke_token(args.agent):
                print("refused: unknown agent", file=sys.stderr)
                return 1
            print(f"token revoked for {args.agent}")
            return 0
        if args.cmd == "show-agent":
            a = show_agent(args.agent)
            if a is None:
                print("not found", file=sys.stderr)
                return 1
            print(json.dumps(a, indent=2, default=str))
            return 0
    except AssertionError as e:
        print(f"SELFTEST FAIL: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # store / usage errors
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
