#!/usr/bin/env python3
"""Marketing web chain — NameCheap -> FlexiFunnels -> free Wix.

Brian's marketing flow (ruled 2026-10-24, PM decision id 100; researched
2026-10-21): every promoted URL is a real domain bought at NameCheap whose
DNS points at FlexiFunnels. FlexiFunnels is the host of record for the
domain, captures the lead (opt-in + webhook), and then sends the visitor
to a FREE Wix site on its wixsite.com subdomain for the long-form
content. This module is the registry of the pieces (domains, funnels,
Wix sites) plus the encoded rules that validate every chain against the
flow — it is the ecosystem's machine-readable understanding of the flow,
and CampaignsDesk reads it through a thin client (never a copy).

Hard rules (violations, not preferences):
  * No Wix premium plans, ever. A free Wix site cannot take a custom
    domain, so NOTHING ever points DNS at Wix.
  * No domains are bought through Wix; the registrar is NameCheap.
  * Capture happens BEFORE Wix — the list is owned regardless of the
    content host.
  * A published Wix site's URL is always a wixsite.com URL.
  * Every funnel redirects to a Wix site; a funnel with no Wix target
    is a broken chain.
  * A funnel may not outrun its domain: 'built' needs the domain's DNS
    set, 'live' needs the domain verified 'Secured' at FlexiFunnels.

State home: PostgreSQL (successbrian_os.marketing_* in
ecosystem_central), beside the PM tables. Canonical prose: AnythingLLM
workspace 'wix' (wix-architecture.md). Idempotent: `init` any time.

CLI:
  init
  add-domain --domain D [--host go] [--dns-target T] [--status S]
  add-wix-site --name N [--url U] [--purpose P] [--status S]
  add-funnel --name N [--domain D] [--funnel-url U] [--capture C]
             [--wix-site NAME] [--status S]
  flow [--domain D | --funnel F]
  validate
  describe
  set-ga --measurement-id G-XXXX [--gtm GTM-XXXX]
  analytics
  add-feature --name N --provider P [--wix-site NAME] [--url U]
              [--purpose P] [--attach link|iframe|api] [--status S]
  features [--wix-site NAME]
  selftest
"""
import argparse
import os
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "pm"))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

import pm_core  # noqa: E402

conn = pm_core.conn

FLOW_SPEC = {
    "name": "NameCheap -> FlexiFunnels -> free Wix",
    "ruled": "Brian, 2026-10-24 (PM decision id 100); researched 2026-10-21",
    "canonical_doc": "AnythingLLM workspace 'wix', wix-architecture.md",
    "steps": [
        "1. DOMAIN (NameCheap): the promoted, professional face. Bought "
        "at NameCheap — never through Wix.",
        "2. DNS -> FlexiFunnels: CNAME (host go/www) -> "
        "target.flexifunnels.com. DNS stops at FlexiFunnels; it is the "
        "host of record and serves HTTPS once verified 'Secured'. "
        "Nothing ever points DNS at Wix.",
        "3. CAPTURE (FlexiFunnels): the funnel page captures the lead "
        "(opt-in + webhook) BEFORE the visitor goes anywhere else — "
        "the list is owned regardless of the content host.",
        "4. CONTENT (free Wix): the funnel redirects to a free Wix site "
        "on its wixsite.com subdomain — long-form detail, proof, video. "
        "The address bar shows wixsite.com after the handoff and free "
        "Wix ads appear; both accepted.",
    ],
    "rules": [
        "No Wix premium plans, ever; no domains bought through Wix.",
        "A free Wix site can never take a custom domain (Wix requires "
        "premium), so no DNS record ever targets Wix.",
        "Every promoted/public URL is a FlexiFunnels URL on a real "
        "NameCheap domain.",
        "Unlimited free Wix subdomains: one content site per offer or "
        "campaign, at zero marginal cost.",
        "Every funnel has a Wix redirect target; capture precedes it.",
    ],
    "analytics": (
        "Analytics layer (verified 2026-10-24): GA4 sits on the "
        "surfaces that can run it — FlexiFunnels (gtag in page "
        "Settings -> Retargeting (Head), or General Code for a whole "
        "funnel) and Substack (publication Settings -> Analytics -> "
        "Google Analytics Measurement ID; views, sign-ups and paid "
        "subscriptions flow as events) — plus Brian's VPS sites "
        "(successbrianvps.com incl. /pm/: full control, gtag in the "
        "frontend code). Free Wix CANNOT run GA (premium-gated), and "
        "nothing may be designed that requires it: the chain measures "
        "Wix via the FlexiFunnels -> Wix handoff (the outbound/redirect "
        "event on the funnel side) plus UTM parameters on the redirect "
        "URL (utm_source=flexifunnels, utm_medium=funnel, "
        "utm_campaign=<campaign slug>); Wix's built-in analytics is "
        "the on-Wix view. GitHub pages/README cannot run GA and are "
        "not a surface."),
    "features": (
        "Feature layer: the Wix site is the content shell; FEATURES "
        "live where the capability fits and attach to the site by "
        "link, iframe, or API. Data-backed features (Postgres, auth, "
        "storage, edge functions — waitlists, member data, app "
        "backends) live on Supabase. JS microsites, serverless "
        "functions and embeddable widgets live on Netlify — also the "
        "free host that DOES allow custom domains when a feature "
        "outgrows an iframe. Live fleet data and APIs live on Brian's "
        "own machines (the VPS and the fleet; the proof is the live "
        "PM dashboard on successbrianvps.com). Features add capability "
        "INSIDE the experience — they never replace the funnel as the "
        "capture point of first contact: capture stays in "
        "FlexiFunnels, per the chain rules."),
}

DOMAIN_STATUS_RANK = {"named": 0, "dns_set": 1, "verified_secured": 2,
                      "live": 3}
# Minimum domain rank a funnel of each status requires.
FUNNEL_MIN_DOMAIN_RANK = {"planned": 0, "built": 1, "live": 2}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS successbrian_os.marketing_domains (
    id          serial PRIMARY KEY,
    domain      text UNIQUE NOT NULL,
    registrar   text NOT NULL DEFAULT 'NameCheap',
    dns_target  text,
    dns_host    text,
    status      text NOT NULL DEFAULT 'named'
                CHECK (status IN ('named','dns_set','verified_secured',
                                   'live')),
    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.marketing_wix_sites (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    wixsite_url text UNIQUE,
    purpose     text,
    status      text NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','building','published')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.marketing_funnels (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    provider    text NOT NULL DEFAULT 'FlexiFunnels',
    domain_id   integer REFERENCES successbrian_os.marketing_domains(id),
    funnel_url  text,
    capture     text,
    campaign    text,
    wix_site_id integer REFERENCES successbrian_os.marketing_wix_sites(id),
    status      text NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','built','live')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE successbrian_os.marketing_funnels
    ADD COLUMN IF NOT EXISTS campaign text;
CREATE TABLE IF NOT EXISTS successbrian_os.marketing_features (
    id          serial PRIMARY KEY,
    wix_site_id integer REFERENCES successbrian_os.marketing_wix_sites(id),
    name        text NOT NULL,
    provider    text NOT NULL
                CHECK (provider IN ('supabase','netlify','own','other')),
    url         text,
    purpose     text,
    attach      text NOT NULL DEFAULT 'link'
                CHECK (attach IN ('link','iframe','api')),
    status      text NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','building','live')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.marketing_analytics (
    id                  serial PRIMARY KEY,
    ga4_measurement_id  text,
    gtm_container_id    text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
"""

# The GA4 possibility map, verified 2026-10-24. 'where' is where the
# measurement ID goes on that surface; surfaces that cannot run GA say
# how the chain measures them instead.
ANALYTICS_SURFACES = [
    {"surface": "flexifunnels", "supported": True,
     "where": "page Settings -> Retargeting (Head) for the gtag "
              "snippet, or General Code to cover a whole funnel at once",
     "note": "fires on the capture side of the chain; the "
             "FlexiFunnels -> Wix redirect is the outbound event"},
    {"surface": "substack", "supported": True,
     "where": "publication Settings -> Analytics -> 'Google "
              "Analytics Measurement ID' field",
     "note": "page views, sign-ups and paid subscriptions flow as "
             "events"},
    {"surface": "wix-free", "supported": False,
     "where": "nowhere — Wix's GA integration and custom code are "
              "premium-gated, and this architecture never buys premium",
     "note": "measured via the FlexiFunnels handoff event + UTM "
             "parameters on the redirect URL; Wix built-in analytics "
             "is the on-Wix view"},
    {"surface": "vps", "supported": True,
     "where": "gtag snippet in the frontend code (full control) — "
              "successbrianvps.com incl. the /pm/ dashboard",
     "note": "supported surface; wiring it is a separate change, not "
             "part of the chain registry"},
    {"surface": "github", "supported": False,
     "where": "nowhere — GitHub pages/README cannot run GA",
     "note": "not a surface"},
]

UTM_SOURCE = "flexifunnels"
UTM_MEDIUM = "funnel"


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "funnel"


def build_redirect_url(wixsite_url, funnel_row):
    """The effective FlexiFunnels -> Wix redirect URL: the Wix site's
    URL carrying the chain's UTM discipline (utm_source=flexifunnels,
    utm_medium=funnel, utm_campaign=<the funnel's campaign slug, or
    its name slugified>). Existing query parameters are preserved and
    existing UTM values are never overwritten or duplicated. Returns
    None when there is no destination URL yet."""
    if not wixsite_url:
        return None
    if isinstance(funnel_row, dict):
        campaign = funnel_row.get("campaign") or \
            slugify(funnel_row.get("funnel_name")
                    or funnel_row.get("name"))
    else:
        campaign = slugify(funnel_row)
    parts = urlsplit(wixsite_url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params.setdefault("utm_source", UTM_SOURCE)
    params.setdefault("utm_medium", UTM_MEDIUM)
    params.setdefault("utm_campaign", campaign)
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(params), parts.fragment))


def get_analytics(cur):
    """The single analytics config row (created empty on demand)."""
    cur.execute("SELECT * FROM successbrian_os.marketing_analytics "
                "ORDER BY id LIMIT 1")
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO successbrian_os.marketing_analytics "
                    "DEFAULT VALUES RETURNING *")
        row = cur.fetchone()
    return dict(row)


def set_ga(cur, measurement_id, gtm=None):
    row = get_analytics(cur)
    cur.execute(
        "UPDATE successbrian_os.marketing_analytics "
        "SET ga4_measurement_id = %s, "
        "    gtm_container_id = COALESCE(%s, gtm_container_id), "
        "    updated_at = now() WHERE id = %s RETURNING *",
        (measurement_id, gtm, row["id"]))
    return dict(cur.fetchone())


def format_analytics(cur):
    cfg = get_analytics(cur)
    ga = cfg.get("ga4_measurement_id")
    lines = ["ANALYTICS — GA4 across the chain (verified 2026-10-24)",
             "measurement ID: %s" % (
                 ga or "NOT SET — minting the GA4 property needs "
                       "Brian's Google sign-in; a missing ID is a "
                       "normal state, not an error"),
             "GTM container: %s" % (cfg.get("gtm_container_id")
                                    or "not set"),
             ""]
    for s in ANALYTICS_SURFACES:
        lines.append("%-12s GA %s — %s" % (
            s["surface"],
            "SUPPORTED" if s["supported"] else "NOT SUPPORTED",
            s["where"]))
        lines.append("%-12s %s" % ("", s["note"]))
    return "\n".join(lines)

SEED_WIX_SITE = {
    "name": "SuccessBrian OS",
    "purpose": "Flagship explainer for SuccessBrian OS: live dashboard "
               "+ blog + GitHub",
    "status": "building",
}


def describe_flow():
    """The canonical flow text — the understanding other code reads."""
    lines = ["MARKETING WEB CHAIN — %s" % FLOW_SPEC["name"],
             "Ruled: %s" % FLOW_SPEC["ruled"],
             "Canonical doc: %s" % FLOW_SPEC["canonical_doc"], ""]
    lines.extend(FLOW_SPEC["steps"])
    lines.append("")
    lines.append("Rules:")
    lines.extend("  - %s" % r for r in FLOW_SPEC["rules"])
    lines.append("")
    lines.append(FLOW_SPEC["analytics"])
    lines.append("")
    lines.append(FLOW_SPEC["features"])
    return "\n".join(lines)


def init_schema(cur):
    cur.execute(SCHEMA_SQL)


SEED_FEATURE = {
    "name": "Live PM dashboard",
    "provider": "own",
    "url": "https://successbrianvps.com/pm/",
    "purpose": "Live operations dashboard — the first own-machine "
               "feature, linked from the SuccessBrian OS Wix site",
    "attach": "link",
    "status": "live",
    "wix_site": "SuccessBrian OS",
}


def seed(cur):
    """Idempotent seeds of the real rows known today."""
    cur.execute(
        """INSERT INTO successbrian_os.marketing_wix_sites
             (name, purpose, status)
           SELECT %(name)s, %(purpose)s, %(status)s
           WHERE NOT EXISTS (
             SELECT 1 FROM successbrian_os.marketing_wix_sites
             WHERE name = %(name)s)""", SEED_WIX_SITE)
    cur.execute(
        """INSERT INTO successbrian_os.marketing_features
             (wix_site_id, name, provider, url, purpose, attach, status)
           SELECT w.id, %(name)s, %(provider)s, %(url)s, %(purpose)s,
                  %(attach)s, %(status)s
             FROM successbrian_os.marketing_wix_sites w
            WHERE w.name = %(wix_site)s
              AND NOT EXISTS (
                SELECT 1 FROM successbrian_os.marketing_features f
                 WHERE f.name = %(name)s)""", SEED_FEATURE)


def add_domain(cur, domain, host=None, dns_target=None, status="named",
               registrar="NameCheap"):
    if dns_target is None:
        dns_target = "target.flexifunnels.com"
    cur.execute(
        """INSERT INTO successbrian_os.marketing_domains
             (domain, registrar, dns_target, dns_host, status)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (domain) DO UPDATE
             SET dns_target=EXCLUDED.dns_target,
                 dns_host=COALESCE(EXCLUDED.dns_host,
                                   marketing_domains.dns_host),
                 status=EXCLUDED.status, updated_at=now()
           RETURNING id""",
        (domain, registrar, dns_target, host, status))
    return cur.fetchone()["id"]


def add_wix_site(cur, name, url=None, purpose=None, status="planned"):
    if url:
        cur.execute(
            """INSERT INTO successbrian_os.marketing_wix_sites
                 (name, wixsite_url, purpose, status)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (wixsite_url) DO UPDATE
                 SET name=EXCLUDED.name, purpose=EXCLUDED.purpose,
                     status=EXCLUDED.status, updated_at=now()
               RETURNING id""", (name, url, purpose, status))
    else:
        cur.execute(
            """INSERT INTO successbrian_os.marketing_wix_sites
                 (name, purpose, status) VALUES (%s, %s, %s)
               RETURNING id""", (name, purpose, status))
    return cur.fetchone()["id"]


def add_funnel(cur, name, domain=None, funnel_url=None, capture=None,
               wix_site=None, status="planned", provider="FlexiFunnels",
               campaign=None):
    domain_id = None
    if domain:
        cur.execute("SELECT id FROM successbrian_os.marketing_domains "
                    "WHERE domain = %s", (domain,))
        row = cur.fetchone()
        if not row:
            raise SystemExit("no such domain in registry: %s" % domain)
        domain_id = row["id"]
    wix_site_id = None
    if wix_site:
        cur.execute("SELECT id FROM successbrian_os.marketing_wix_sites "
                    "WHERE name = %s", (wix_site,))
        row = cur.fetchone()
        if not row:
            raise SystemExit("no such Wix site in registry: %s" % wix_site)
        wix_site_id = row["id"]
    cur.execute(
        """INSERT INTO successbrian_os.marketing_funnels
             (name, provider, domain_id, funnel_url, capture, campaign,
              wix_site_id, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (name, provider, domain_id, funnel_url, capture, campaign,
         wix_site_id, status))
    return cur.fetchone()["id"]


FEATURE_PROVIDERS = ("supabase", "netlify", "own", "other")


def add_feature(cur, name, provider, wix_site=None, url=None,
                purpose=None, attach="link", status="planned"):
    wix_site_id = None
    if wix_site:
        cur.execute("SELECT id FROM successbrian_os.marketing_wix_sites "
                    "WHERE name = %s", (wix_site,))
        row = cur.fetchone()
        if not row:
            raise SystemExit("no such Wix site in registry: %s"
                             % wix_site)
        wix_site_id = row["id"]
    cur.execute(
        """INSERT INTO successbrian_os.marketing_features
             (wix_site_id, name, provider, url, purpose, attach, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (wix_site_id, name, provider, url, purpose, attach, status))
    return cur.fetchone()["id"]


def fetch_features(cur, wix_site=None):
    """All registered features, each with its Wix site's name."""
    sql = ("SELECT f.*, w.name AS wix_name "
           "FROM successbrian_os.marketing_features f "
           "LEFT JOIN successbrian_os.marketing_wix_sites w "
           "ON w.id = f.wix_site_id")
    if wix_site:
        cur.execute(sql + " WHERE w.name = %s ORDER BY f.id",
                    (wix_site,))
    else:
        cur.execute(sql + " ORDER BY f.id")
    return [dict(r) for r in cur.fetchall()]


def validate_feature(f):
    """Violations for one feature row/dict. Features are EXTERNAL by
    definition — they add the capabilities a free Wix site cannot do
    itself, so 'wix' as a provider is a category error; and a feature
    claiming to be live must have somewhere to point."""
    violations = []
    if (f.get("provider") or "").lower() == "wix":
        violations.append(
            "feature '%s' claims provider 'wix' — features are "
            "external by definition (supabase/netlify/own/other); the "
            "free Wix site is the content shell, never a feature "
            "provider" % f.get("name"))
    if f.get("status") == "live" and not f.get("url"):
        violations.append(
            "feature '%s' is live but has no URL — a live feature "
            "must have somewhere for the link/iframe/API to point"
            % f.get("name"))
    return violations


def format_features(features):
    lines = []
    for f in features:
        lines.append("  - '%s' [%s] provider=%s attach=%s %s" % (
            f["name"], f["status"], f["provider"], f["attach"],
            f.get("url") or "(no URL yet)"))
        if f.get("purpose"):
            lines.append("      %s" % f["purpose"])
    return lines


def fetch_chains(cur):
    """Every chain, composed: one dict per funnel, plus loose ends."""
    cur.execute(
        """SELECT f.id AS funnel_id, f.name AS funnel_name,
                  f.provider, f.funnel_url, f.capture, f.campaign,
                  f.status AS funnel_status,
                  d.id AS domain_id, d.domain, d.registrar, d.dns_host,
                  d.dns_target, d.status AS domain_status,
                  w.id AS wix_id, w.name AS wix_name, w.wixsite_url,
                  w.purpose AS wix_purpose, w.status AS wix_status
             FROM successbrian_os.marketing_funnels f
             LEFT JOIN successbrian_os.marketing_domains d
               ON d.id = f.domain_id
             LEFT JOIN successbrian_os.marketing_wix_sites w
               ON w.id = f.wix_site_id
            ORDER BY f.id""")
    funnels = [dict(r) for r in cur.fetchall()]
    cur.execute(
        """SELECT d.* FROM successbrian_os.marketing_domains d
            WHERE NOT EXISTS (
              SELECT 1 FROM successbrian_os.marketing_funnels f
               WHERE f.domain_id = d.id) ORDER BY d.id""")
    loose_domains = [dict(r) for r in cur.fetchall()]
    cur.execute(
        """SELECT w.* FROM successbrian_os.marketing_wix_sites w
            WHERE NOT EXISTS (
              SELECT 1 FROM successbrian_os.marketing_funnels f
               WHERE f.wix_site_id = w.id) ORDER BY w.id""")
    loose_wix = [dict(r) for r in cur.fetchall()]
    return {"funnels": funnels, "domains_without_funnel": loose_domains,
            "wix_sites_without_funnel": loose_wix}


def validate_chain(chain):
    """(violations, warnings) for one composed funnel chain."""
    violations, warnings = [], []
    name = chain.get("funnel_name") or "?"
    if not chain.get("wix_id"):
        violations.append(
            "funnel '%s' has no Wix redirect target — every funnel must "
            "hand the visitor to a free Wix site after capture" % name)
    fstatus = chain.get("funnel_status") or "planned"
    need = FUNNEL_MIN_DOMAIN_RANK.get(fstatus, 0)
    if need > 0:
        if not chain.get("domain_id"):
            violations.append(
                "funnel '%s' is %s but has no domain — a promoted "
                "funnel needs a NameCheap domain on FlexiFunnels"
                % (name, fstatus))
        else:
            have = DOMAIN_STATUS_RANK.get(chain.get("domain_status"), 0)
            if have < need:
                violations.append(
                    "funnel '%s' is %s but its domain %s is only '%s' "
                    "(needs at least '%s') — funnel status outruns "
                    "domain status" % (
                        name, fstatus, chain.get("domain"),
                        chain.get("domain_status"),
                        [k for k, v in DOMAIN_STATUS_RANK.items()
                         if v == need][0]))
    target = (chain.get("dns_target") or "").lower()
    if chain.get("domain_id") and "wix" in target:
        violations.append(
            "domain %s points DNS at Wix (%s) — FORBIDDEN: DNS stops "
            "at FlexiFunnels; a free Wix site can never take a custom "
            "domain" % (chain.get("domain"), chain.get("dns_target")))
    if chain.get("wix_id") and chain.get("wix_status") == "published":
        url = chain.get("wixsite_url") or ""
        if "wixsite.com" not in url:
            violations.append(
                "Wix site '%s' is published but its URL (%s) is not a "
                "wixsite.com URL — published Wix sites are always free "
                "subdomains" % (chain.get("wix_name"), url or "none"))
    # UTM discipline: free Wix runs no GA, so the handoff IS the
    # measurement — the effective redirect URL must carry all three
    # UTM parameters. Missing on a live funnel is a violation; not
    # yet complete on a non-live funnel is a warning.
    effective = build_redirect_url(chain.get("wixsite_url"), chain)
    if effective:
        q = dict(parse_qsl(urlsplit(effective).query))
        missing = [p for p in ("utm_source", "utm_medium",
                               "utm_campaign") if not q.get(p)]
    else:
        missing = ["utm_source", "utm_medium", "utm_campaign"]
    if missing:
        msg = ("funnel '%s': effective redirect URL lacks UTM "
               "attribution (%s) — the FlexiFunnels -> Wix handoff "
               "must carry utm_source/utm_medium/utm_campaign because "
               "free Wix cannot run GA" % (name, ", ".join(missing)))
        if fstatus == "live":
            violations.append(msg)
        elif chain.get("wix_id"):
            warnings.append(msg + " (not live yet)")
    return violations, warnings


def validate_all(cur):
    """Validate every chain plus registry-wide rules. Returns
    (violations, warnings) as lists of strings."""
    chains = fetch_chains(cur)
    violations, warnings = [], []
    for ch in chains["funnels"]:
        v, w = validate_chain(ch)
        violations.extend(v)
        warnings.extend(w)
    # Rule (c) also applies to domains with no funnel yet.
    for d in chains["domains_without_funnel"]:
        if "wix" in (d.get("dns_target") or "").lower():
            violations.append(
                "domain %s points DNS at Wix (%s) — FORBIDDEN: DNS "
                "stops at FlexiFunnels" % (d["domain"], d["dns_target"]))
    # Rule (d) also applies to Wix sites with no funnel yet.
    for w in chains["wix_sites_without_funnel"]:
        if w["status"] == "published" and \
                "wixsite.com" not in (w.get("wixsite_url") or ""):
            violations.append(
                "Wix site '%s' is published but its URL (%s) is not a "
                "wixsite.com URL" % (w["name"], w.get("wixsite_url")))
        warnings.append(
            "Wix site '%s' (%s) has no funnel pointing at it — orphan "
            "content until a FlexiFunnels chain sends it visitors"
            % (w["name"], w["status"]))
    for f in fetch_features(cur):
        violations.extend(validate_feature(f))
    return violations, warnings


def format_chain(chain):
    dom = chain.get("domain")
    if dom:
        dom_line = "%s [%s] DNS %s -> %s" % (
            dom, chain.get("domain_status"),
            (chain.get("dns_host") or "@"), chain.get("dns_target"))
    else:
        dom_line = "(no domain yet)"
    wix = chain.get("wix_name")
    if wix:
        wix_line = "%s [%s] %s" % (wix, chain.get("wix_status"),
                                   chain.get("wixsite_url")
                                   or "(URL not published yet)")
    else:
        wix_line = "(no Wix target — BROKEN)"
    redirect = build_redirect_url(chain.get("wixsite_url"), chain)
    return ("CHAIN '%s' [%s]\n"
            "  domain  : %s\n"
            "  funnel  : %s (%s) capture: %s\n"
            "  wix     : %s\n"
            "  redirect: %s" % (
                chain.get("funnel_name"), chain.get("funnel_status"),
                dom_line, chain.get("funnel_url") or "(no URL yet)",
                chain.get("provider"), chain.get("capture") or "-",
                wix_line, redirect or "(none — no destination URL yet)"))


def selftest():
    """In-transaction exercise of add/flow/validate incl. deliberate
    violations; rolls back. Prints PASS per assertion."""
    results = []

    def check(cond, label):
        results.append((bool(cond), label))
        print("%s %s" % ("PASS" if cond else "FAIL", label))

    c = conn()
    try:
        cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        init_schema(cur)
        did = add_domain(cur, "selftest-chain.example", host="go",
                         status="verified_secured")
        wid = add_wix_site(cur, "Selftest Content",
                           url="https://acct.wixsite.com/selftest",
                           purpose="selftest", status="published")
        add_funnel(cur, "Selftest Funnel", domain="selftest-chain.example",
                   funnel_url="https://go.selftest-chain.example/",
                   capture="email opt-in + webhook",
                   wix_site="Selftest Content", status="live")
        chains = fetch_chains(cur)
        mine = [ch for ch in chains["funnels"]
                if ch["funnel_name"] == "Selftest Funnel"]
        check(len(mine) == 1 and mine[0]["domain_id"] == did
              and mine[0]["wix_id"] == wid,
              "flow composes domain -> funnel -> wix")
        v, _ = validate_chain(mine[0])
        check(v == [], "clean chain validates with no violations")

        # Deliberate violation (c): DNS pointed at Wix.
        cur.execute("UPDATE successbrian_os.marketing_domains "
                    "SET dns_target = 'evil.wixsite.com' WHERE id = %s",
                    (did,))
        chains = fetch_chains(cur)
        mine = [ch for ch in chains["funnels"]
                if ch["funnel_name"] == "Selftest Funnel"][0]
        v, _ = validate_chain(mine)
        check(any("points DNS at Wix" in x for x in v),
              "violation caught: DNS target at Wix")
        cur.execute("UPDATE successbrian_os.marketing_domains "
                    "SET dns_target = 'target.flexifunnels.com' "
                    "WHERE id = %s", (did,))

        # Deliberate violation (a): funnel with no Wix target.
        cur.execute("UPDATE successbrian_os.marketing_funnels "
                    "SET wix_site_id = NULL "
                    "WHERE name = 'Selftest Funnel'")
        chains = fetch_chains(cur)
        mine = [ch for ch in chains["funnels"]
                if ch["funnel_name"] == "Selftest Funnel"][0]
        v, _ = validate_chain(mine)
        check(any("no Wix redirect target" in x for x in v),
              "violation caught: funnel without Wix target")

        # Deliberate violation (b): live funnel, domain only 'named'.
        cur.execute("UPDATE successbrian_os.marketing_funnels "
                    "SET wix_site_id = %s WHERE name = 'Selftest Funnel'",
                    (wid,))
        cur.execute("UPDATE successbrian_os.marketing_domains "
                    "SET status = 'named' WHERE id = %s", (did,))
        chains = fetch_chains(cur)
        mine = [ch for ch in chains["funnels"]
                if ch["funnel_name"] == "Selftest Funnel"][0]
        v, _ = validate_chain(mine)
        check(any("outruns" in x for x in v),
              "violation caught: funnel status outruns domain status")
        cur.execute("UPDATE successbrian_os.marketing_domains "
                    "SET status = 'verified_secured' WHERE id = %s",
                    (did,))

        # UTM discipline.
        u = build_redirect_url("https://acct.wixsite.com/selftest",
                               {"campaign": "selftest-launch",
                                "funnel_name": "Selftest Funnel"})
        q = dict(parse_qsl(urlsplit(u).query))
        check(q.get("utm_source") == "flexifunnels"
              and q.get("utm_medium") == "funnel"
              and q.get("utm_campaign") == "selftest-launch",
              "redirect URL carries all three UTM params")
        u2 = build_redirect_url("https://acct.wixsite.com/x?ref=ad",
                                {"funnel_name": "My Funnel"})
        q2 = dict(parse_qsl(urlsplit(u2).query))
        check(q2.get("ref") == "ad"
              and q2.get("utm_campaign") == "my-funnel",
              "existing query string preserved; campaign falls back "
              "to slugified funnel name")
        u3 = build_redirect_url(
            "https://acct.wixsite.com/x?utm_source=partner",
            {"campaign": "c1", "funnel_name": "F"})
        check(u3.count("utm_source") == 1
              and "utm_source=partner" in u3,
              "existing UTM values kept, never duplicated")
        check(build_redirect_url(None, {"funnel_name": "F"}) is None,
              "no destination URL -> no redirect URL")

        # Live funnel whose Wix target has no URL yet: the effective
        # redirect cannot carry UTMs — violation must fire.
        cur.execute("UPDATE successbrian_os.marketing_wix_sites "
                    "SET wixsite_url = NULL, status = 'building' "
                    "WHERE id = %s", (wid,))
        chains = fetch_chains(cur)
        mine = [ch for ch in chains["funnels"]
                if ch["funnel_name"] == "Selftest Funnel"][0]
        v, _ = validate_chain(mine)
        check(any("UTM" in x for x in v),
              "violation caught: live funnel missing UTM attribution")

        # Analytics with no ID set is a normal, clean state.
        cfg = get_analytics(cur)
        check(cfg.get("ga4_measurement_id") is None,
              "analytics config with NULL measurement ID is clean")
        txt = format_analytics(cur)
        check("NOT SET" in txt and "wix-free" in txt
              and "NOT SUPPORTED" in txt,
              "analytics report renders with NULL ID + surface map")

        # Feature layer.
        add_feature(cur, "Selftest Waitlist", "supabase",
                    wix_site="Selftest Content",
                    url="https://example.supabase.co/waitlist",
                    purpose="selftest", attach="api", status="live")
        add_feature(cur, "Selftest Ghost", "netlify",
                    wix_site="Selftest Content", status="live")
        feats = {f["name"]: f for f in fetch_features(cur)}
        check(validate_feature(feats["Selftest Waitlist"]) == [],
              "live feature with URL validates clean")
        check(any("no URL" in x
                  for x in validate_feature(feats["Selftest Ghost"])),
              "violation caught: live feature without URL")
        check(any("external by definition" in x
                  for x in validate_feature(
                      {"name": "Selftest Fake", "provider": "wix",
                       "status": "planned", "url": None})),
              "violation caught: feature claiming provider 'wix'")
    finally:
        c.rollback()
        c.close()
    failed = [lbl for ok, lbl in results if not ok]
    if failed:
        print("SELFTEST FAIL: %d assertion(s)" % len(failed))
        return 1
    print("SELFTEST PASS (%d assertions)" % len(results))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="web_chain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    d = sub.add_parser("add-domain")
    d.add_argument("--domain", required=True)
    d.add_argument("--host")
    d.add_argument("--dns-target")
    d.add_argument("--status", default="named",
                   choices=sorted(DOMAIN_STATUS_RANK))
    w = sub.add_parser("add-wix-site")
    w.add_argument("--name", required=True)
    w.add_argument("--url")
    w.add_argument("--purpose")
    w.add_argument("--status", default="planned",
                   choices=["planned", "building", "published"])
    f = sub.add_parser("add-funnel")
    f.add_argument("--name", required=True)
    f.add_argument("--domain")
    f.add_argument("--funnel-url")
    f.add_argument("--capture")
    f.add_argument("--wix-site")
    f.add_argument("--campaign")
    f.add_argument("--status", default="planned",
                   choices=sorted(FUNNEL_MIN_DOMAIN_RANK))
    sg = sub.add_parser("set-ga")
    sg.add_argument("--measurement-id", required=True)
    sg.add_argument("--gtm")
    sub.add_parser("analytics")
    fe = sub.add_parser("add-feature")
    fe.add_argument("--name", required=True)
    fe.add_argument("--provider", required=True,
                    choices=list(FEATURE_PROVIDERS))
    fe.add_argument("--wix-site")
    fe.add_argument("--url")
    fe.add_argument("--purpose")
    fe.add_argument("--attach", default="link",
                    choices=["link", "iframe", "api"])
    fe.add_argument("--status", default="planned",
                    choices=["planned", "building", "live"])
    fl2 = sub.add_parser("features")
    fl2.add_argument("--wix-site")
    fl = sub.add_parser("flow")
    fl.add_argument("--domain")
    fl.add_argument("--funnel")
    sub.add_parser("validate")
    sub.add_parser("describe")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "describe":
        print(describe_flow())
        return 0

    c = conn()
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    init_schema(cur)
    if args.cmd == "init":
        seed(cur)
        c.commit()
        print("marketing web chain registry ready: marketing_domains, "
              "marketing_funnels, marketing_wix_sites (seeded: "
              "SuccessBrian OS Wix site)")
    elif args.cmd == "add-domain":
        rid = add_domain(cur, args.domain, host=args.host,
                         dns_target=args.dns_target, status=args.status)
        c.commit()
        print("domain id=%d %s [%s]" % (rid, args.domain, args.status))
    elif args.cmd == "add-wix-site":
        rid = add_wix_site(cur, args.name, url=args.url,
                           purpose=args.purpose, status=args.status)
        c.commit()
        print("wix site id=%d %s [%s]" % (rid, args.name, args.status))
    elif args.cmd == "add-funnel":
        rid = add_funnel(cur, args.name, domain=args.domain,
                         funnel_url=args.funnel_url,
                         capture=args.capture, wix_site=args.wix_site,
                         status=args.status, campaign=args.campaign)
        c.commit()
        print("funnel id=%d %s [%s]" % (rid, args.name, args.status))
    elif args.cmd == "set-ga":
        row = set_ga(cur, args.measurement_id, gtm=args.gtm)
        c.commit()
        print("analytics config: measurement ID %s, GTM %s"
              % (row["ga4_measurement_id"],
                 row.get("gtm_container_id") or "not set"))
    elif args.cmd == "analytics":
        print(format_analytics(cur))
    elif args.cmd == "add-feature":
        rid = add_feature(cur, args.name, args.provider,
                          wix_site=args.wix_site, url=args.url,
                          purpose=args.purpose, attach=args.attach,
                          status=args.status)
        c.commit()
        print("feature id=%d '%s' provider=%s [%s]"
              % (rid, args.name, args.provider, args.status))
    elif args.cmd == "features":
        feats = fetch_features(cur, wix_site=args.wix_site)
        if args.wix_site:
            print("FEATURES for Wix site '%s':" % args.wix_site)
        if not feats:
            print("  (none registered)")
        for line in format_features(feats):
            print(line)
    elif args.cmd == "flow":
        chains = fetch_chains(cur)
        rows = chains["funnels"]
        if args.funnel:
            rows = [r for r in rows if r["funnel_name"] == args.funnel]
        if args.domain:
            rows = [r for r in rows if r["domain"] == args.domain]
        if not rows:
            print("no matching chain")
        for r in rows:
            print(format_chain(r))
            v, w_ = validate_chain(r)
            for x in v:
                print("  VIOLATION: %s" % x)
            for x in w_:
                print("  warning: %s" % x)
            if not v:
                print("  verdict: chain OK")
        features = fetch_features(cur)
        by_site = {}
        for f in features:
            by_site.setdefault(f.get("wix_name") or "(fleet general)",
                               []).append(f)
        print("FEATURES BY WIX SITE:")
        if not by_site:
            print("  (none registered)")
        for site, fs in by_site.items():
            print(" %s:" % site)
            for line in format_features(fs):
                print(line)
    elif args.cmd == "validate":
        violations, warnings = validate_all(cur)
        for x in violations:
            print("VIOLATION: %s" % x)
        for x in warnings:
            print("warning: %s" % x)
        print("validate: %d violation(s), %d warning(s)"
              % (len(violations), len(warnings)))
        if violations:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
