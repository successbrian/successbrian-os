#!/usr/bin/env python3
"""
identity_resolution — SuccessBrian OS core Identity Resolution module.

PURPOSE: Resolve whether social profiles on different surfaces belong
    to the same person, grade that judgment with evidence, remember
    rejected pairs forever, protect Brian-ruled fields from overwrite,
    and flag lookalike / clone / namesake risk — without merging or
    deleting any person record.

WHY: Brian's order (2026-11-08): take the best ecosystem-fit ideas
    from the PingCRM audit and build them into SuccessBrian OS, plus
    his same-day addition that the system must be smart about
    lookalikes and clones and determine the correct accounts. Before
    this module, graded cross-platform matches lived only in markdown;
    no alpha database held a pairwise match with evidence, a grade,
    and a review state. PingCRM is AGPL-3.0, so this is a clean-room
    implementation written from the audit's descriptions and design
    parameters only — no PingCRM code was read or copied by the
    builder of this module.

    Placement law (Brian, 2026-10-29): People is SuccessBrian OS core
    (the basic contact manager plus the identity machinery that keeps
    it true). The deep layer (Rolodex, pipelines) remains
    ContactFlowCRM's; this module feeds it, never impersonates it.
    Mapping-only: nothing here sends, contacts, follows, or acts.
    Account actions on a flagged lookalike are Brian's alone.

CALLED BY: agents and the friend-vetting daily run, from the repo
    tree: python3 tools/ecosystem_intel/identity_resolution.py <flag>
    State lives in PostgreSQL database people_unified, schema people,
    tables identity_people / identity_profiles / identity_matches /
    identity_bio_snapshots / identity_life_events (NEW tables only;
    no existing table is altered). DB access goes through
    sbos_common with an explicit dbname="people_unified".

NOTES:
    - Links, never merges: profiles are linked to an identity_people
      anchor; every grade change leaves an identity_matches audit row;
      unmerge is always possible because nothing is deleted.
    - Same-source exclusion is law: two profiles on the SAME platform
      with distinct platform_ids are never a same_person pair. They
      route to the lookalike scan instead.
    - A REJECTED / ruled_different pair is remembered forever and is
      never re-surfaced by --resolve.
    - Brian-pinned fields: identity_people.pinned_fields names the
      facts Brian has ruled; upsert paths refuse to overwrite them and
      record the conflict as evidence instead.
    - Lookalike verdicts: owner_variant / likely_clone / namesake /
      unresolved. WHICH FIELD differs matters: a variant confined to
      the username while the display name is correct is the
      owner-variant pattern; clones copy the display name and vary
      the username. Cross-platform content sync (identical original
      posts, same day) is the strongest same-person signal short of
      owner confirmation — it is a coded signal slot that stays
      UNKNOWN in v1 list data, never fabricated. Depth differential
      and account-vintage signals are scored when data exists.
    - First validated lookalike case (2026-11-08): Zach Loescher —
      SAME PERSON, self-chosen variant spelling confined to the
      Facebook vanity username (ZLoesher1); the Instagram handle
      (zloescher1) and both display names spell Loescher correctly.
    - Life-event classification from bio diffs is keyword rules,
      honestly labeled method='rules-v1'. An LLM classifier is a
      later upgrade, not a silent assumption.
    - UNKNOWN stays UNKNOWN: a signal with no data is recorded as
      UNKNOWN in the evidence, never as a negative.

CLI:
    python3 identity_resolution.py --init-schema
    python3 identity_resolution.py --import-profiles <json>
    python3 identity_resolution.py --resolve
    python3 identity_resolution.py --queue
    python3 identity_resolution.py --stats
    python3 identity_resolution.py --selftest
    python3 identity_resolution.py --rule-same <profile_id> <profile_id>
    python3 identity_resolution.py --rule-different <profile_id> <profile_id>

Brian's rulings (2026-11-08, written back via --rule-same /
--rule-different):
    - 100% confident = Brian-confirmed or deterministic matches ONLY.
      An engine score, even >= 0.85, is never 100%. On a 100% match
      the canonical identity_people.display_name is written with the
      CORRECT spelling and pinned (pinned_fields) so no sync can
      overwrite it; misspellings are preserved as recorded variants
      in the match signals, never silently deleted. Handles and
      profile URLs are identifiers, NOT names — they are never
      rewritten (facebook.com/ZLoesher1 stays exactly as-is).
    - Breadth = value: identity_people carries profile_count /
      platform_count / surface_count, recomputed on every resolve
      and ruling, counting only CONFIRMED/STRONG graded links (a
      POSSIBLE link raises nothing; a second handle on the same
      platform raises profile_count but not platform_count). The
      queue surfaces multi-surface people first. This is a value /
      priority signal for Brian's attention and enrichment order —
      not a relationship score, not an outreach trigger.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
import sbos_common  # noqa: E402

DBNAME = "people_unified"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "identity_resolution_schema.sql")

PLATFORMS = {
    "facebook", "instagram", "threads", "messenger", "whatsapp",
    "telegram", "linkedin", "x", "tiktok", "youtube", "email", "other",
}

PLATFORM_MAP = {
    "facebook": "facebook", "fb": "facebook", "facebook.com": "facebook",
    "instagram": "instagram", "ig": "instagram",
    "instagram.com": "instagram",
    "threads": "threads", "threads.net": "threads",
    "threads.com": "threads",
    "messenger": "messenger", "m.me": "messenger",
    "whatsapp": "whatsapp", "wa": "whatsapp",
    "telegram": "telegram", "t.me": "telegram",
    "linkedin": "linkedin", "linkedin.com": "linkedin",
    "x": "x", "twitter": "x", "twitter.com": "x", "x.com": "x",
    "tiktok": "tiktok", "tiktok.com": "tiktok",
    "youtube": "youtube", "youtube.com": "youtube", "youtu.be": "youtube",
    "email": "email", "mail": "email",
}

GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "aol.com", "proton.me", "protonmail.com",
    "live.com", "msn.com", "gmx.com", "mail.com",
}

STOPWORDS = {
    "the", "and", "for", "with", "your", "you", "are", "our", "all",
    "this", "that", "from", "into", "life", "live", "daily", "more",
    "about", "welcome", "official", "page", "real",
}

SIGNAL_WEIGHTS = {
    "identical_handle": 0.35,
    "name_similarity": 0.25,
    "handle_similarity": 0.15,
    "location_agreement": 0.10,
    "bio_overlap": 0.10,
    "shared_context": 0.05,
}

EVENT_RULES = [
    ("product_launch", 0.80,
     ("launching", "launched", "just launched", "new product",
      "introducing", "now live")),
    ("promotion", 0.80, ("promoted", "promotion", "new role as")),
    ("job_change", 0.75,
     ("new job", "joined", "now at", "working at", "excited to join",
      "starting at")),
    ("company_change", 0.70,
     ("founder of", "ceo of", "owner of", "director at", "now with")),
    ("new_offer", 0.65,
     ("now offering", "now coaching", "new program", "enrolling",
      "booking clients", "work with me")),
    ("relocation", 0.65,
     ("moved to", "relocated to", "based in", "now living in")),
    ("milestone", 0.55,
     ("anniversary", "years sober", "sober since", "followers",
      "milestone", "celebrating")),
]


# ------------------------------------------------------------------ db

def _conn():
    return sbos_common.connect(dbname=DBNAME)


def _dict_conn():
    import psycopg2.extras
    conn = _conn()
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def init_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        sql = fh.read()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    finally:
        conn.close()
    print("schema applied: people.identity_people, "
          "people.identity_profiles, people.identity_matches, "
          "people.identity_bio_snapshots, people.identity_life_events")


# ------------------------------------------------------- normalization

def canonical_platform(value):
    if value is None:
        return "other"
    key = str(value).strip().lower().strip("@")
    key = re.sub(r"^https?://", "", key)
    key = key.split("/")[0] if "." in key else key
    if key in PLATFORM_MAP:
        return PLATFORM_MAP[key]
    raw = str(value).strip().lower().strip("@")
    return PLATFORM_MAP.get(raw, "other")


def normalize_handle(value):
    """handle_norm: lowercase, strip leading @, strip trailing separators."""
    if value is None:
        return None
    handle = str(value).strip().lower()
    handle = handle.lstrip("@").strip()
    handle = re.sub(r"[._\-~]+$", "", handle)
    return handle or None


def handle_root(handle_norm):
    """handle_root: handle_norm minus trailing digits (zloescher1 -> zloescher)."""
    if not handle_norm:
        return None
    root = re.sub(r"[0-9]+$", "", handle_norm)
    return root or handle_norm


def normalize_name(value):
    """name_norm: lowercase tokens, punctuation dropped, order kept."""
    if value is None:
        return ""
    text = str(value).lower()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def name_tokens(value):
    return [t for t in normalize_name(value).split() if t]


def surname_of(value):
    tokens = name_tokens(value)
    return tokens[-1] if tokens else None


def levenshtein(a, b):
    """Fresh Levenshtein edit distance (two-row dynamic program)."""
    a = a or ""
    b = b or ""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[-1]


def string_similarity(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    dist = levenshtein(a, b)
    return max(0.0, 1.0 - dist / max(len(a), len(b)))


def name_similarity(name_a, name_b):
    """Token-aware name similarity.

    Exact token equality = 1.0. One token set contained in the other
    (e.g. 'Zach Loescher' vs 'Zach Loescher - Soberpreneur') = 0.95.
    Otherwise the better of full-string and sorted-token similarity.
    """
    tokens_a = name_tokens(name_a)
    tokens_b = name_tokens(name_b)
    if not tokens_a or not tokens_b:
        return 0.0
    set_a, set_b = set(tokens_a), set(tokens_b)
    if set_a == set_b:
        return 1.0
    if set_a < set_b or set_b < set_a:
        return 0.95
    joined_a = " ".join(tokens_a)
    joined_b = " ".join(tokens_b)
    sorted_a = " ".join(sorted(tokens_a))
    sorted_b = " ".join(sorted(tokens_b))
    return max(string_similarity(joined_a, joined_b),
               string_similarity(sorted_a, sorted_b))


def bio_tokens(bio):
    if not bio:
        return set()
    words = re.findall(r"[a-z0-9][a-z0-9']+", str(bio).lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def extract_email_domain(profile):
    email = profile.get("email")
    if email and "@" in str(email):
        return str(email).lower().rsplit("@", 1)[-1].strip()
    bio = profile.get("bio") or profile.get("bio_current") or ""
    found = re.search(r"[\w.+-]+@([\w-]+\.[\w.]+)", str(bio))
    return found.group(1).lower() if found else None


def _get(profile, *keys):
    for key in keys:
        value = profile.get(key)
        if value is not None and value != "":
            return value
    return None


def profile_handle(profile):
    return normalize_handle(_get(profile, "handle_norm", "handle",
                                 "username"))


def profile_name(profile):
    return _get(profile, "display_name", "name") or ""


def profile_bio(profile):
    return _get(profile, "bio_current", "bio", "biography")


def profile_location(profile):
    return _get(profile, "location", "current_location")


# ------------------------------------------------------ pinned fields

def protected_person_updates(existing, incoming, pinned_fields):
    """Split incoming person-field updates into (accepted, refused).

    pinned_fields is either a dict of field -> Brian-ruled value, or a
    list of field names Brian has ruled. A conflicting incoming value
    for a pinned field is refused (the caller stores it as evidence /
    a note, never as an overwrite). Unpinned fields pass through.
    """
    pinned = pinned_fields or {}
    accepted, refused = {}, {}
    for field, value in (incoming or {}).items():
        if value is None:
            continue
        is_pinned = field in pinned
        if is_pinned:
            ruled = pinned[field] if isinstance(pinned, dict) else existing.get(field)
            if ruled is not None and normalize_name(str(ruled)) != \
                    normalize_name(str(value)) and \
                    str(ruled).strip() != str(value).strip():
                refused[field] = {
                    "incoming": value, "pinned_value": ruled,
                    "reason": "brian_pinned_field",
                }
                continue
        accepted[field] = value
    return accepted, refused


# ------------------------------------------------------------- scoring

def grade_for_score(score):
    if score is None:
        return None
    if score >= 0.85:
        return "CONFIRMED"
    if score >= 0.70:
        return "STRONG"
    if score >= 0.50:
        return "POSSIBLE"
    return None


def _shared_context_value(a, b):
    """1.0 when a shared-context fact exists, else None (UNKNOWN)."""
    for profile in (a, b):
        anchors = profile.get("shared_anchors")
        if anchors:
            other = b if profile is a else a
            other_anchors = other.get("shared_anchors")
            if other_anchors is None or set(anchors) & set(other_anchors):
                return 1.0
    ctx_a = _get(a, "context_key", "source_group", "shared_context")
    ctx_b = _get(b, "context_key", "source_group", "shared_context")
    if ctx_a is not None and ctx_b is not None:
        if isinstance(ctx_a, bool) or isinstance(ctx_b, bool):
            return 1.0 if (ctx_a and ctx_b) else None
        return 1.0 if str(ctx_a) == str(ctx_b) else None
    if a.get("shared_context") is True and b.get("shared_context") is True:
        return 1.0
    return None


def score_pair(a, b):
    """Score a candidate pair of profile dicts.

    Returns a dict: score, grade, status, signals. The signals dict is
    the evidence — every signal that fired, with its value, weight and
    contribution, plus the caps that were applied and the slots that
    are UNKNOWN. Weights redistribute across the signals that are
    actually available (adaptive redistribution).
    """
    platform_a = canonical_platform(a.get("platform"))
    platform_b = canonical_platform(b.get("platform"))
    id_a = a.get("platform_id")
    id_b = b.get("platform_id")
    content_sync = _get(a, "content_sync")
    if content_sync is None:
        content_sync = _get(b, "content_sync")
    signals = {
        "platforms": [platform_a, platform_b],
        "content_sync": content_sync if content_sync is not None
        else "UNKNOWN",
    }

    # Same-source exclusion — law, not a score.
    if platform_a == platform_b:
        if id_a is not None and id_b is not None and str(id_a) != str(id_b):
            signals["same_source_exclusion"] = {
                "rule": "same platform, distinct platform_ids",
                "platform": platform_a,
            }
            return {"score": Decimal("0"), "grade": "EXCLUDED",
                    "status": "auto", "signals": signals}
        return {"score": None, "grade": None, "status": None,
                "signals": signals, "skip": "same profile surface"}

    # Deterministic cross-references.
    email_a = _get(a, "email")
    email_b = _get(b, "email")
    if email_a and email_b and str(email_a).lower() == str(email_b).lower():
        signals["deterministic"] = "identical_email"
        return {"score": Decimal("1"), "grade": "CONFIRMED",
                "status": "auto", "signals": signals}
    if id_a is not None and id_b is not None and str(id_a) == str(id_b) \
            and {platform_a, platform_b} in ({"instagram", "threads"},
                                             {"facebook", "messenger"}):
        signals["deterministic"] = \
            "shared_meta_platform_id (shared id namespace: " \
            + "/".join(sorted((platform_a, platform_b))) + ")"
        return {"score": Decimal("1"), "grade": "CONFIRMED",
                "status": "auto", "signals": signals}
    linked_a = a.get("linked_platform_ids") or {}
    linked_b = b.get("linked_platform_ids") or {}
    if (isinstance(linked_a, dict)
            and str(linked_a.get(platform_b)) == str(id_b) and id_b) or \
       (isinstance(linked_b, dict)
            and str(linked_b.get(platform_a)) == str(id_a) and id_a):
        signals["deterministic"] = "explicit_platform_id_cross_reference"
        return {"score": Decimal("1"), "grade": "CONFIRMED",
                "status": "auto", "signals": signals}
    if a.get("brian_confirmed_pair") and b.get("brian_confirmed_pair"):
        signals["deterministic"] = "brian_ruling"
        return {"score": Decimal("1"), "grade": "CONFIRMED",
                "status": "ruled_same", "signals": signals}

    handle_a = profile_handle(a)
    handle_b = profile_handle(b)
    name_a = profile_name(a)
    name_b = profile_name(b)

    values = {}
    if handle_a and handle_b and handle_a == handle_b:
        values["identical_handle"] = 1.0
    sim_name = None
    if name_a and name_b:
        sim_name = name_similarity(name_a, name_b)
        values["name_similarity"] = round(sim_name, 4)
    if handle_a and handle_b and "identical_handle" not in values:
        values["handle_similarity"] = round(
            string_similarity(handle_a, handle_b), 4)
    loc_a = profile_location(a)
    loc_b = profile_location(b)
    if loc_a and loc_b:
        loc_tokens_a = set(name_tokens(loc_a))
        loc_tokens_b = set(name_tokens(loc_b))
        values["location_agreement"] = round(
            jaccard(loc_tokens_a, loc_tokens_b), 4) if loc_tokens_a \
            and loc_tokens_b else 0.0
    else:
        signals["location_agreement"] = "UNKNOWN"
    bio_a = profile_bio(a)
    bio_b = profile_bio(b)
    if bio_a and bio_b:
        values["bio_overlap"] = round(
            jaccard(bio_tokens(bio_a), bio_tokens(bio_b)), 4)
    else:
        signals["bio_overlap"] = "UNKNOWN"
    shared_ctx = _shared_context_value(a, b)
    if shared_ctx is not None:
        values["shared_context"] = shared_ctx
    else:
        signals["shared_context"] = "UNKNOWN"

    if not values:
        return {"score": None, "grade": None, "status": None,
                "signals": signals, "skip": "no comparable signals"}

    available_weight = sum(SIGNAL_WEIGHTS[k] for k in values)
    weighted = sum(SIGNAL_WEIGHTS[k] * v for k, v in values.items())
    score = weighted / available_weight if available_weight else 0.0

    fired = {}
    for key, value in values.items():
        fired[key] = {
            "value": value, "weight": SIGNAL_WEIGHTS[key],
            "contribution": round(SIGNAL_WEIGHTS[key] * value, 4),
        }
    signals["fired"] = fired
    signals["available_weight"] = round(available_weight, 4)

    # Guard caps.
    caps = []
    surname_a = surname_of(name_a)
    surname_b = surname_of(name_b)
    # Descriptor-suffixed display names ('Zach Loescher - Soberpreneur')
    # put the surname mid-name; when one name's token set contains the
    # other's, the contained name defines the surname for both sides.
    _tokens_a = name_tokens(name_a)
    _tokens_b = name_tokens(name_b)
    if _tokens_a and _tokens_b:
        if set(_tokens_a) <= set(_tokens_b):
            surname_a = surname_b = _tokens_a[-1]
        elif set(_tokens_b) <= set(_tokens_a):
            surname_a = surname_b = _tokens_b[-1]
    if surname_a and surname_b and surname_a != surname_b:
        caps.append(("conflicting_surnames", 0.35))
    tokens_a = name_tokens(name_a)
    tokens_b = name_tokens(name_b)
    if (tokens_a and len(tokens_a) == 1) or (tokens_b and len(tokens_b) == 1):
        caps.append(("single_token_name", 0.50))
    if set(values) == {"name_similarity"}:
        caps.append(("name_only_evidence", 0.65))
    if sim_name is not None and sim_name < 0.50 and (
            "shared_context" in values or "bio_overlap" in values):
        caps.append(("shared_context_with_dissimilar_names", 0.35))
    for cap_name, cap_value in caps:
        if score > cap_value:
            score = cap_value
    if caps:
        signals["caps_applied"] = [
            {"cap": name, "max_score": value} for name, value in caps]

    score = round(score, 4)
    grade = grade_for_score(score)
    status = "pending_review" if grade == "POSSIBLE" else "auto"
    return {"score": Decimal(str(score)), "grade": grade,
            "status": status, "signals": signals}


def is_100_confident(result_or_match):
    """Brian's ruling (2026-11-08): 100% confident means Brian-
    confirmed or deterministic (shared platform_id cross-reference /
    Brian ruling written back). An engine score — even >= 0.85 — is
    never 100% on its own."""
    if not result_or_match:
        return False
    signals = result_or_match.get("signals") or {}
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except ValueError:
            signals = {}
    if signals.get("deterministic"):
        return True
    if result_or_match.get("method") == "brian":
        return True
    if result_or_match.get("status") == "ruled_same":
        return True
    return False


def correct_canonical_name(existing_name, profile_names, qualifying):
    """Name-correction gate (Brian, 2026-11-08).

    Only a 100%-confident match (qualifying=True) may correct the
    canonical name. The correct spelling is taken from the profiles'
    DISPLAY NAMES — never from handles, which are identifiers. The
    core name is the token set contained in the most profile names
    (a descriptor-suffixed name like 'Zach Loescher - Soberpreneur'
    supports the core 'Zach Loescher'). Misspelled variants are
    returned so the caller can preserve them as evidence.
    """
    result = {"display_name": existing_name, "corrected": False,
              "pinned": False, "variants": []}
    if not qualifying:
        return result
    cores = []
    for name in profile_names:
        tokens = name_tokens(name)
        if tokens:
            cores.append((name, tokens))
    best = None
    for name, tokens in cores:
        token_set = set(tokens)
        support = sum(1 for _n, other in cores
                      if token_set <= set(other))
        rank = (support, -len(tokens))
        if best is None or rank > best[0]:
            best = (rank, name, tokens)
    if best is None:
        return result
    _rank, core_name, core_tokens = best
    core_norm = " ".join(core_tokens)
    corrected = core_name if set(name_tokens(core_name)) == set(core_tokens) \
        else core_norm.title()
    # Use the exact display casing of a profile whose name IS the core.
    for name, tokens in cores:
        if tokens == core_tokens:
            corrected = name
            break
    variants = []
    if existing_name and normalize_name(existing_name) != core_norm:
        variants.append({"field": "person_record", "recorded": existing_name,
                         "kind": "misspelled_name_variant"})
    for name, tokens in cores:
        if set(tokens) == set(core_tokens) or set(core_tokens) < set(tokens):
            continue
        if levenshtein(normalize_name(name), core_norm) <= 3:
            variants.append({"field": "display_name", "recorded": name,
                             "kind": "misspelled_name_variant"})
    result.update({"display_name": corrected, "corrected": True,
                   "pinned": True, "variants": variants})
    return result


def handle_name_variants(profiles, canonical_name):
    """Recorded handle variants: a handle whose root is a near-miss
    of the canonical surname is a misspelling preserved as evidence.
    The handle itself is an identifier and is NEVER rewritten."""
    surname = surname_of(canonical_name)
    variants = []
    if not surname:
        return variants
    for profile in profiles:
        handle_norm = profile_handle(profile)
        if not handle_norm:
            continue
        root = handle_root(handle_norm)
        if surname not in handle_norm and root and \
                levenshtein(root, surname) <= 2:
            variants.append({
                "field": "handle", "profile_id": profile.get("id"),
                "platform": canonical_platform(profile.get("platform")),
                "recorded": profile.get("handle"),
                "canonical_surname": surname,
                "kind": "misspelled_handle_variant_preserved_as_identifier",
            })
    return variants


def compute_breadth(profiles, matches):
    """Breadth = value (Brian, 2026-11-08): a person's value signal
    rises with each additional CONFIRMED/STRONG linked profile.

    Pure function. profiles: dicts with id, person_id, platform.
    matches: dicts/tuples with profile_a_id, profile_b_id, grade,
    status. Only graded links count — a profile counts toward its
    person's breadth only when a CONFIRMED/STRONG same-person match
    (status auto or ruled_same) ties it to another profile of the
    SAME person. A POSSIBLE-only link raises nothing. Returns
    {person_id: {profile_count, platform_count, surface_count}} —
    profile and platform counts are exposed separately, never
    blended: a second handle on the same platform (Sandy Loeven's
    two Instagram accounts) raises profile_count but not
    platform_count. This is a value/priority signal for Brian's
    attention and enrichment order — NOT a relationship score and
    NOT an outreach trigger (mapping-only)."""
    by_id = {p["id"]: p for p in profiles if p.get("person_id")}
    supported = set()
    for match in matches or []:
        if isinstance(match, dict):
            grade = match.get("grade")
            status = match.get("status")
            id_a = match.get("profile_a_id", match.get("a"))
            id_b = match.get("profile_b_id", match.get("b"))
        else:
            id_a, id_b, grade, status = match
        if grade not in ("CONFIRMED", "STRONG"):
            continue
        if status not in ("auto", "ruled_same"):
            continue
        pa = by_id.get(id_a)
        pb = by_id.get(id_b)
        if pa and pb and pa["person_id"] == pb["person_id"]:
            supported.add(id_a)
            supported.add(id_b)
    out = {}
    for pid in supported:
        profile = by_id[pid]
        entry = out.setdefault(profile["person_id"], {
            "profile_count": 0, "platforms": set(), "surface_count": 0})
        entry["profile_count"] += 1
        entry["platforms"].add(canonical_platform(profile.get("platform")))
    for entry in out.values():
        entry["platform_count"] = len(entry.pop("platforms"))
        entry["surface_count"] = entry["profile_count"]
    return out


def person_value_rank(breadth_entry):
    """Queue priority: multi-surface people surface first (the
    ENRICHMENT_QUEUE ordering law — most matched profiles first)."""
    if not breadth_entry:
        return (0, 0)
    return (breadth_entry.get("profile_count", 0),
            breadth_entry.get("platform_count", 0))


def pair_is_suppressed(existing_match):
    """Rejected-pair memory: a ruled_different / REJECTED pair is
    never re-surfaced by the resolver."""
    if not existing_match:
        return False
    return existing_match.get("grade") == "REJECTED" or \
        existing_match.get("status") == "ruled_different"


# --------------------------------------------------- lookalike / clone

def _post_count(profile):
    return _get(profile, "post_count", "posts_count", "posts")


def _account_vintage(profile):
    vintage = _get(profile, "account_vintage", "vintage")
    if vintage:
        return str(vintage)
    platform = canonical_platform(profile.get("platform"))
    pid = profile.get("platform_id")
    if platform == "facebook" and pid and str(pid).startswith("1000"):
        return "facebook 1000x-era numeric id"
    if pid:
        return "platform_id present (era UNKNOWN)"
    return None


def is_lookalike_candidate(a, b):
    handle_a = profile_handle(a)
    handle_b = profile_handle(b)
    if not handle_a and not handle_b:
        return False
    name_same = normalize_name(profile_name(a)) == \
        normalize_name(profile_name(b)) and bool(profile_name(a))
    if handle_a and handle_b:
        if handle_a == handle_b:
            # Identical handles across platforms are the normal
            # same-person pattern; they become a lookalike candidate
            # only when the display names materially conflict.
            sim = name_similarity(profile_name(a), profile_name(b))
            return bool(profile_name(a) and profile_name(b) and sim < 0.5)
        if levenshtein(handle_a, handle_b) <= 2:
            return True
        root_a = handle_root(handle_a)
        root_b = handle_root(handle_b)
        if root_a == root_b:
            return True
        if name_same and string_similarity(handle_a, handle_b) >= 0.65:
            return True
    if name_same and handle_a and handle_b:
        return string_similarity(handle_a, handle_b) >= 0.5
    return False


def classify_lookalike(a, b, same_person_score=None):
    """Classify a lookalike candidate pair.

    Verdicts: owner_variant / likely_clone / namesake / unresolved.
    Field-level comparison: WHICH FIELD differs is itself evidence —
    a variant confined to the username while both display names are
    correct is the owner-variant pattern (Zach Loescher, validated
    2026-11-08); clones copy the display name and vary the username,
    so a same-platform duplicate with thin/divergent signals leans
    clone; same name + similar handle + a different world is the
    common namesake case and gets its own outcome.
    """
    platform_a = canonical_platform(a.get("platform"))
    platform_b = canonical_platform(b.get("platform"))
    same_platform = platform_a == platform_b
    handle_a = profile_handle(a)
    handle_b = profile_handle(b)
    name_a = profile_name(a)
    name_b = profile_name(b)
    surname = surname_of(name_a) or surname_of(name_b)

    display_tokens_a = set(name_tokens(name_a))
    display_tokens_b = set(name_tokens(name_b))
    display_core_same = bool(display_tokens_a and display_tokens_b) and (
        display_tokens_a <= display_tokens_b
        or display_tokens_b <= display_tokens_a
        or display_tokens_a == display_tokens_b)
    surname_in_both_displays = bool(surname) and surname in display_tokens_a \
        and surname in display_tokens_b
    surname_in_handle_a = bool(surname and handle_a and surname in handle_a)
    surname_in_handle_b = bool(surname and handle_b and surname in handle_b)
    username_only_variant = display_core_same and handle_a != handle_b \
        and surname_in_both_displays

    bio_a = profile_bio(a)
    bio_b = profile_bio(b)
    bio_sim = jaccard(bio_tokens(bio_a), bio_tokens(bio_b)) \
        if bio_a and bio_b else None
    bio_copied = bio_sim is not None and bio_sim >= 0.80
    worlds_disjoint = bool(
        bio_a and bio_b and len(bio_tokens(bio_a)) >= 4
        and len(bio_tokens(bio_b)) >= 4 and bio_sim is not None
        and bio_sim <= 0.10)
    loc_a = profile_location(a)
    loc_b = profile_location(b)
    location_conflict = bool(
        loc_a and loc_b
        and not (set(name_tokens(loc_a)) & set(name_tokens(loc_b))))

    followers_a = _get(a, "followers")
    followers_b = _get(b, "followers")
    follower_asymmetry = None
    if followers_a and followers_b:
        low, high = min(followers_a, followers_b), max(followers_a, followers_b)
        follower_asymmetry = round(low / high, 4) if high else None
    posts_a = _post_count(a)
    posts_b = _post_count(b)
    depth_ratio = None
    if posts_a is not None and posts_b is not None and max(posts_a, posts_b):
        depth_ratio = round(min(posts_a, posts_b) / max(posts_a, posts_b), 4)
    thin_side = (posts_a is not None and posts_a <= 5) or \
        (posts_b is not None and posts_b <= 5) or \
        (follower_asymmetry is not None and follower_asymmetry < 0.10
         and not posts_a and not posts_b)

    content_sync = _get(a, "content_sync")
    if content_sync is None:
        content_sync = _get(b, "content_sync")
    anchors_a = a.get("shared_anchors") or []
    anchors_b = b.get("shared_anchors") or []
    shared_anchors = sorted(set(anchors_a) & set(anchors_b)) \
        if anchors_a and anchors_b else []
    anchors_conflict = a.get("anchors_conflict") is True or \
        b.get("anchors_conflict") is True

    signals = {
        "verdict_basis": {
            "same_platform": same_platform,
            "platforms": [platform_a, platform_b],
            "handle_edit_distance": levenshtein(handle_a or "", handle_b or ""),
            "field_that_differs": "username_only" if username_only_variant
            else ("display_name" if not display_core_same else "none"),
            "display_name_core_same": display_core_same,
            "surname_correct_in_both_display_names": surname_in_both_displays,
            "surname_in_handles": [surname_in_handle_a, surname_in_handle_b],
            "bio_similarity": None if bio_sim is None else round(bio_sim, 4),
            "bio_copied": bio_copied,
            "follower_asymmetry": follower_asymmetry,
            "depth_ratio": depth_ratio,
            "post_counts": [posts_a, posts_b],
            "account_vintage": [_account_vintage(a), _account_vintage(b)],
            "content_sync": content_sync if content_sync is not None
            else "UNKNOWN",
            "same_person_score": float(same_person_score)
            if same_person_score is not None else "UNKNOWN",
            "shared_anchors": shared_anchors,
            "worlds_disjoint": worlds_disjoint,
            "location_conflict": location_conflict,
            "activity_presence": "UNKNOWN" if posts_a is None
            and posts_b is None else "observed",
        }
    }

    namesake_evidence = (worlds_disjoint or location_conflict
                         or anchors_conflict) \
        and not shared_anchors and content_sync is not True
    owner_evidence = (not same_platform and username_only_variant) and (
        content_sync is True or bool(shared_anchors)
        or (surname_in_both_displays and depth_ratio is not None
            and depth_ratio > 0)
        or (same_person_score is not None
            and float(same_person_score) >= 0.85))

    if namesake_evidence:
        verdict = "namesake"
    elif owner_evidence:
        verdict = "owner_variant"
    elif same_platform and (bio_copied or thin_side or follower_asymmetry
                            is not None and follower_asymmetry < 0.25):
        verdict = "likely_clone"
    else:
        verdict = "unresolved"

    signals["verdict"] = verdict
    if verdict == "owner_variant":
        grade, status = "STRONG", "auto"
    elif verdict == "namesake":
        grade, status = "POSSIBLE", "auto"
    elif verdict == "likely_clone":
        grade, status = "POSSIBLE", "pending_review"
    else:
        grade, status = "POSSIBLE", "pending_review"
    return {"verdict": verdict, "grade": grade, "status": status,
            "signals": signals}


# --------------------------------------------------------- bio events

def classify_bio_change(old_bio, new_bio):
    """Keyword-rules life-event classification (method='rules-v1').

    Honest v1: explicit phrases in the NEW bio fire a category with a
    fixed confidence; a bio that changed with no phrase match is an
    'other' event at low confidence. Returns a list of event dicts.
    """
    old_bio = old_bio or ""
    new_bio = new_bio or ""
    if old_bio == new_bio:
        return []
    text = " " + new_bio.lower() + " "
    events = []
    for event_type, confidence, phrases in EVENT_RULES:
        hit = next((p for p in phrases if p in text), None)
        if hit:
            events.append({
                "event_type": event_type,
                "confidence": confidence,
                "summary": f"Bio change matched rules-v1 phrase "
                           f"'{hit}' ({event_type}).",
                "method": "rules-v1",
                "matched_phrase": hit,
            })
            break
    if not events:
        added = sorted(bio_tokens(new_bio) - bio_tokens(old_bio))[:8]
        events.append({
            "event_type": "other",
            "confidence": 0.40,
            "summary": "Bio changed; no rules-v1 category phrase matched. "
                       f"New terms: {', '.join(added) or 'UNKNOWN'}.",
            "method": "rules-v1",
            "matched_phrase": None,
        })
    return events


# -------------------------------------------------------------- import

def _bio_hash(bio):
    return hashlib.sha256((bio or "").encode("utf-8")).hexdigest()


def _snapshot_bio(cur, profile_id, bio, source):
    """Capture a bio snapshot on change; diff into life events."""
    if bio is None:
        return None
    digest = _bio_hash(bio)
    cur.execute(
        "SELECT bio, bio_hash FROM people.identity_bio_snapshots "
        "WHERE profile_id=%s ORDER BY captured_at DESC, id DESC LIMIT 1",
        (profile_id,))
    latest = cur.fetchone()
    if latest and latest["bio_hash"] == digest:
        return None
    cur.execute(
        "INSERT INTO people.identity_bio_snapshots "
        "(profile_id, bio, bio_hash, source) VALUES (%s, %s, %s, %s) "
        "RETURNING id", (profile_id, bio, digest, source))
    snapshot_id = cur.fetchone()["id"]
    if latest is not None:
        for event in classify_bio_change(latest["bio"], bio):
            cur.execute(
                "INSERT INTO people.identity_life_events "
                "(profile_id, event_type, confidence, summary, old_bio, "
                "new_bio, method) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (profile_id, event["event_type"], event["confidence"],
                 event["summary"], latest["bio"], bio, event["method"]))
    return snapshot_id


def import_profiles(path):
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload.get("profiles") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("import file must be a JSON list of profiles "
                         "(or an object with a 'profiles' list)")
    inserted = updated = skipped = snapshots = 0
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        for raw in rows:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            platform = canonical_platform(raw.get("platform"))
            platform_id = raw.get("platform_id")
            platform_id = str(platform_id) if platform_id is not None \
                and str(platform_id) != "" else None
            handle = _get(raw, "handle", "username")
            handle_norm = normalize_handle(handle)
            display_name = _get(raw, "display_name", "name")
            if not platform_id and not handle_norm and not display_name:
                skipped += 1
                continue
            bio = _get(raw, "bio", "biography")
            source = raw.get("source")

            existing = None
            if platform_id:
                cur.execute(
                    "SELECT * FROM people.identity_profiles "
                    "WHERE platform=%s AND platform_id=%s",
                    (platform, platform_id))
                existing = cur.fetchone()
            if existing is None and handle_norm:
                # Platform-ID backfill path: a handle-known profile with
                # no ID yet absorbs the ID this import reveals, so the
                # next pass is deterministic.
                cur.execute(
                    "SELECT * FROM people.identity_profiles "
                    "WHERE platform=%s AND handle_norm=%s "
                    "ORDER BY (platform_id IS NOT NULL) DESC, id LIMIT 1",
                    (platform, handle_norm))
                candidate = cur.fetchone()
                if candidate and (candidate["platform_id"] is None
                                  or platform_id is None
                                  or str(candidate["platform_id"])
                                  == platform_id):
                    existing = candidate
            if existing is None and raw.get("profile_url"):
                cur.execute(
                    "SELECT * FROM people.identity_profiles "
                    "WHERE platform=%s AND profile_url=%s LIMIT 1",
                    (platform, raw["profile_url"]))
                existing = cur.fetchone()

            if existing is None:
                cur.execute(
                    "INSERT INTO people.identity_profiles "
                    "(platform, platform_id, handle, handle_norm, "
                    "display_name, profile_url, followers, following, "
                    "bio_current, source) VALUES (%s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s) RETURNING id",
                    (platform, platform_id, handle, handle_norm,
                     display_name, raw.get("profile_url"),
                     _get(raw, "followers"), _get(raw, "following"),
                     bio, source))
                profile_id = cur.fetchone()["id"]
                inserted += 1
            else:
                profile_id = existing["id"]
                # Pinned-field protection: if this profile is linked
                # to a person whose display_name Brian has pinned, an
                # incoming conflicting display name is evidence only —
                # it never overwrites the profile's ruled display.
                effective_display = display_name
                if existing.get("person_id"):
                    cur.execute(
                        "SELECT display_name, pinned_fields FROM "
                        "people.identity_people WHERE id=%s",
                        (existing["person_id"],))
                    person = cur.fetchone()
                    pinned = (person or {}).get("pinned_fields") or {}
                    if isinstance(pinned, str):
                        pinned = json.loads(pinned)
                    if person and "display_name" in pinned:
                        effective_display = person["display_name"]
                cur.execute(
                    "UPDATE people.identity_profiles SET "
                    "platform_id=COALESCE(platform_id, %s), "
                    "handle=COALESCE(%s, handle), "
                    "handle_norm=COALESCE(%s, handle_norm), "
                    "display_name=%s, "
                    "profile_url=COALESCE(%s, profile_url), "
                    "followers=COALESCE(%s, followers), "
                    "following=COALESCE(%s, following), "
                    "bio_current=COALESCE(%s, bio_current), "
                    "source=COALESCE(%s, source), last_seen=now() "
                    "WHERE id=%s",
                    (platform_id, handle, handle_norm,
                     effective_display,
                     raw.get("profile_url"), _get(raw, "followers"),
                     _get(raw, "following"), bio, source, profile_id))
                updated += 1
            if _snapshot_bio(cur, profile_id, bio, source) is not None:
                snapshots += 1
        conn.commit()
    finally:
        conn.close()
    print(f"import: {inserted} inserted, {updated} updated, "
          f"{skipped} skipped, {snapshots} bio snapshots captured "
          f"from {path}")
    return {"inserted": inserted, "updated": updated,
            "skipped": skipped, "snapshots": snapshots}


# ------------------------------------------------------------- resolve

def _pair_key(id_a, id_b):
    return (min(id_a, id_b), max(id_a, id_b))


def _blocking_keys(profile):
    keys = set()
    handle_norm = profile_handle(profile)
    if handle_norm:
        keys.add(("handle_norm", handle_norm))
        keys.add(("handle_root", handle_root(handle_norm)))
    tokens = name_tokens(profile_name(profile))
    for token in tokens:
        keys.add(("name_token", token))
    surname = surname_of(profile_name(profile))
    if surname:
        keys.add(("surname", surname))
    domain = extract_email_domain(profile)
    if domain:
        keys.add(("email_domain", domain))
    if profile.get("platform_id") is not None:
        keys.add(("platform_id", str(profile["platform_id"])))
    return keys


def _upsert_match(cur, kind, id_a, id_b, score, grade, signals, method,
                  status):
    low, high = _pair_key(id_a, id_b)
    cur.execute(
        "INSERT INTO people.identity_matches "
        "(kind, profile_a_id, profile_b_id, score, grade, signals, "
        "method, status) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s) "
        "ON CONFLICT (kind, profile_a_id, profile_b_id) DO UPDATE SET "
        "score=EXCLUDED.score, grade=EXCLUDED.grade, "
        "signals=EXCLUDED.signals, method=EXCLUDED.method, "
        "status=EXCLUDED.status, updated_at=now() "
        "WHERE people.identity_matches.status NOT IN "
        "('ruled_same', 'ruled_different') "
        "AND people.identity_matches.grade <> 'REJECTED'",
        (kind, low, high, score, grade, json.dumps(signals), method,
         status))


def recompute_breadth(cur):
    """Recompute identity_people breadth from graded links only."""
    cur.execute("SELECT id, person_id, platform FROM "
                "people.identity_profiles WHERE person_id IS NOT NULL")
    profiles = cur.fetchall()
    cur.execute("SELECT profile_a_id, profile_b_id, grade, status "
                "FROM people.identity_matches WHERE kind='same_person'")
    matches = cur.fetchall()
    breadth = compute_breadth(profiles, matches)
    cur.execute("UPDATE people.identity_people SET profile_count=0, "
                "platform_count=0, surface_count=0, updated_at=now()")
    for person_id, entry in breadth.items():
        cur.execute(
            "UPDATE people.identity_people SET profile_count=%s, "
            "platform_count=%s, surface_count=%s, updated_at=now() "
            "WHERE id=%s",
            (entry["profile_count"], entry["platform_count"],
             entry["surface_count"], person_id))
    return breadth


def _apply_name_correction(cur, person, member_profiles, qualifying_pairs):
    """On a 100%-confident component: write the canonical name with
    the correct spelling, pin it, and preserve misspelled variants
    as evidence on the qualifying match rows. Handles/URLs are
    identifiers and are never touched."""
    names = [p["display_name"] for p in member_profiles
             if p.get("display_name")]
    correction = correct_canonical_name(person["display_name"], names,
                                        qualifying=True)
    if not correction["corrected"]:
        return None
    pinned = person.get("pinned_fields") or {}
    if isinstance(pinned, str):
        pinned = json.loads(pinned)
    pinned["display_name"] = correction["display_name"]
    cur.execute(
        "UPDATE people.identity_people SET display_name=%s, "
        "name_norm=%s, pinned_fields=%s::jsonb, updated_at=now() "
        "WHERE id=%s",
        (correction["display_name"],
         normalize_name(correction["display_name"]),
         json.dumps(pinned), person["id"]))
    variants = list(correction["variants"])
    variants.extend(handle_name_variants(member_profiles,
                                         correction["display_name"]))
    if variants:
        for id_a, id_b in qualifying_pairs:
            low, high = _pair_key(id_a, id_b)
            cur.execute(
                "SELECT signals FROM people.identity_matches WHERE "
                "kind='same_person' AND profile_a_id=%s AND "
                "profile_b_id=%s", (low, high))
            row = cur.fetchone()
            if row:
                signals = row["signals"]
                if isinstance(signals, str):
                    signals = json.loads(signals)
                signals["name_variants"] = variants
                signals["name_correction"] = {
                    "canonical_name": correction["display_name"],
                    "basis": "100% confident match (Brian ruling, "
                             "2026-11-08): canonical name written "
                             "with the correct spelling and pinned; "
                             "variants preserved as evidence; "
                             "handles/URLs untouched",
                }
                cur.execute(
                    "UPDATE people.identity_matches SET "
                    "signals=%s::jsonb, updated_at=now() WHERE "
                    "kind='same_person' AND profile_a_id=%s AND "
                    "profile_b_id=%s",
                    (json.dumps(signals), low, high))
    return correction


def apply_ruling(profile_a_id, profile_b_id, ruling, ruled_by="brian"):
    """Write back a Brian ruling on a pair (ruled_same/ruled_different).

    ruled_same is a 100%-confident match: the pair is linked, the
    canonical name is corrected + pinned, and misspelled variants
    are preserved on the match signals. ruled_different writes the
    REJECTED memory — the pair is never re-surfaced."""
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM people.identity_profiles "
                    "WHERE id IN (%s, %s)", (profile_a_id, profile_b_id))
        profiles = cur.fetchall()
        if len(profiles) != 2:
            raise ValueError("both profile ids must exist")
        low, high = _pair_key(profile_a_id, profile_b_id)
        if ruling == "different":
            _upsert_match(cur, "same_person", low, high, Decimal("0"),
                          "REJECTED", {"ruling": "ruled_different",
                                       "basis": "Brian ruling written "
                                                "back; pair never "
                                                "re-surfaced"},
                          "brian", "ruled_different")
            cur.execute(
                "UPDATE people.identity_matches SET resolved_by=%s, "
                "resolved_at=now() WHERE kind='same_person' AND "
                "profile_a_id=%s AND profile_b_id=%s",
                (ruled_by, low, high))
            conn.commit()
            print(f"ruling written: profiles {low} + {high} = "
                  f"ruled_different (REJECTED, never re-surfaced)")
            return
        _upsert_match(cur, "same_person", low, high, Decimal("1"),
                      "CONFIRMED",
                      {"deterministic": "brian_ruling",
                       "ruling": "ruled_same"},
                      "brian", "ruled_same")
        cur.execute(
            "UPDATE people.identity_matches SET resolved_by=%s, "
            "resolved_at=now() WHERE kind='same_person' AND "
            "profile_a_id=%s AND profile_b_id=%s",
            (ruled_by, low, high))
        existing_people = sorted({p["person_id"] for p in profiles
                                  if p["person_id"]})
        person = None
        if existing_people:
            cur.execute("SELECT * FROM people.identity_people "
                        "WHERE id = ANY(%s) ORDER BY brian_confirmed "
                        "DESC, id LIMIT 1", (existing_people,))
            person = cur.fetchone()
        if person is None:
            names = [p["display_name"] for p in profiles
                     if p["display_name"]]
            correction = correct_canonical_name(None, names, True)
            display = correction["display_name"] or \
                (profiles[0]["handle"] or "UNKNOWN")
            cur.execute(
                "INSERT INTO people.identity_people (display_name, "
                "name_norm, brian_confirmed) VALUES (%s, %s, TRUE) "
                "RETURNING *", (display, normalize_name(display)))
            person = cur.fetchone()
        else:
            cur.execute("UPDATE people.identity_people SET "
                        "brian_confirmed=TRUE, updated_at=now() "
                        "WHERE id=%s", (person["id"],))
            person["brian_confirmed"] = True
        for profile in profiles:
            cur.execute("UPDATE people.identity_profiles SET "
                        "person_id=%s WHERE id=%s",
                        (person["id"], profile["id"]))
        correction = _apply_name_correction(
            cur, person, profiles, [(low, high)])
        recompute_breadth(cur)
        conn.commit()
        print(f"ruling written: profiles {low} + {high} = ruled_same "
              f"(100% confident); person {person['id']} canonical name "
              f"'{(correction or {}).get('display_name', person['display_name'])}'"
              f"{', corrected + pinned' if correction else ''}; "
              f"handles/URLs untouched")
    finally:
        conn.close()


def _strong_same_platform_candidate(a, b):
    if normalize_name(profile_name(a)) and \
            normalize_name(profile_name(a)) == normalize_name(profile_name(b)):
        return True
    handle_a = profile_handle(a)
    handle_b = profile_handle(b)
    if handle_a and handle_b:
        if handle_a == handle_b or handle_root(handle_a) == handle_root(handle_b):
            return True
        if levenshtein(handle_a, handle_b) <= 2:
            return True
    return False


def resolve():
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM people.identity_profiles ORDER BY id")
        profiles = cur.fetchall()
        by_id = {p["id"]: p for p in profiles}

        cur.execute("SELECT kind, profile_a_id, profile_b_id, grade, "
                    "status, method FROM people.identity_matches")
        existing = {}
        for row in cur.fetchall():
            existing[(row["kind"], row["profile_a_id"],
                      row["profile_b_id"])] = row

        blocks = defaultdict(list)
        for profile in profiles:
            for key in _blocking_keys(profile):
                blocks[key].append(profile["id"])
        candidate_pairs = set()
        for key, ids in blocks.items():
            if len(ids) > 500:
                continue
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    candidate_pairs.add(_pair_key(ids[i], ids[j]))

        counts = {"pairs_considered": 0, "same_person_written": 0,
                  "lookalike_written": 0, "suppressed_rejected": 0,
                  "below_threshold": 0}
        eligible_links = []

        for id_a, id_b in sorted(candidate_pairs):
            a = by_id[id_a]
            b = by_id[id_b]
            counts["pairs_considered"] += 1
            prior_same = existing.get(("same_person", id_a, id_b))
            if pair_is_suppressed(prior_same):
                counts["suppressed_rejected"] += 1
                continue
            prior_brian = prior_same and (
                prior_same.get("method") == "brian"
                or prior_same.get("status") in ("ruled_same",
                                                "ruled_different"))

            platform_a = canonical_platform(a.get("platform"))
            platform_b = canonical_platform(b.get("platform"))
            if platform_a == platform_b:
                if _strong_same_platform_candidate(a, b):
                    result = score_pair(a, b)
                    if result["grade"] == "EXCLUDED" and not prior_brian:
                        _upsert_match(
                            cur, "same_person", id_a, id_b,
                            result["score"], "EXCLUDED",
                            result["signals"], "engine", "auto")
                        counts["same_person_written"] += 1
            else:
                if prior_brian and prior_same.get("status") == "ruled_same":
                    eligible_links.append((1.0, id_a, id_b, True))
                result = score_pair(a, b)
                if result.get("skip"):
                    counts["below_threshold"] += 1
                elif result["grade"] is None:
                    counts["below_threshold"] += 1
                elif not prior_brian:
                    _upsert_match(
                        cur, "same_person", id_a, id_b, result["score"],
                        result["grade"], result["signals"], "engine",
                        result["status"])
                    counts["same_person_written"] += 1
                    if result["grade"] in ("CONFIRMED", "STRONG"):
                        eligible_links.append(
                            (float(result["score"]), id_a, id_b,
                             is_100_confident(result)))

            # Lookalike scan (both same-platform and cross-platform).
            prior_look = existing.get(("lookalike_risk", id_a, id_b))
            prior_look_brian = prior_look and (
                prior_look.get("method") == "brian"
                or prior_look.get("status") in ("ruled_same",
                                                "ruled_different"))
            if not prior_look_brian and is_lookalike_candidate(a, b):
                _same_score = None
                if platform_a != platform_b:
                    _same_result = score_pair(a, b)
                    _same_score = _same_result.get("score")
                look = classify_lookalike(a, b,
                                          same_person_score=_same_score)
                _upsert_match(
                    cur, "lookalike_risk", id_a, id_b, None,
                    look["grade"], look["signals"], "engine",
                    look["status"])
                counts["lookalike_written"] += 1

        # Link eligible profiles to identity_people anchors
        # (union-find; links only — nothing is merged or deleted).
        parent = {p["id"]: p["id"] for p in profiles}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def component_members(root):
            return [pid for pid, r in
                    ((pid, find(pid)) for pid in parent) if r == root]

        pair_qualifying = {}
        for _s, _a, _b, _q in eligible_links:
            pair_qualifying[_pair_key(_a, _b)] = _q
        linked_people = 0
        for _score, id_a, id_b, _qual in sorted(
                eligible_links,
                key=lambda item: item[0], reverse=True):
            root_a, root_b = find(id_a), find(id_b)
            if root_a == root_b:
                continue
            members = component_members(root_a) + component_members(root_b)
            platforms_seen = {}
            conflict = False
            for pid in members:
                plat = canonical_platform(by_id[pid].get("platform"))
                plat_id = by_id[pid].get("platform_id")
                if plat in platforms_seen and plat_id is not None \
                        and platforms_seen[plat] is not None \
                        and str(platforms_seen[plat]) != str(plat_id):
                    conflict = True
                    break
                platforms_seen.setdefault(plat, plat_id)
            if conflict:
                continue
            parent[root_b] = root_a

        components = defaultdict(list)
        for profile in profiles:
            components[find(profile["id"])].append(profile["id"])
        for _root, members in components.items():
            if len(members) < 2:
                continue
            member_profiles = [by_id[m] for m in members]
            existing_people = sorted(
                {p["person_id"] for p in member_profiles if p["person_id"]})
            canonical_person = None
            if existing_people:
                cur.execute(
                    "SELECT * FROM people.identity_people WHERE id = ANY(%s) "
                    "ORDER BY brian_confirmed DESC, id LIMIT 1",
                    (existing_people,))
                canonical_person = cur.fetchone()
            if canonical_person is None:
                _names = [p["display_name"] for p in member_profiles
                          if p["display_name"]]
                if _names:
                    display = min(
                        _names,
                        key=lambda n: (len(name_tokens(n)), len(n)))
                else:
                    display = next(
                        (p["handle"] for p in member_profiles
                         if p["handle"]), "UNKNOWN")
                cur.execute(
                    "INSERT INTO people.identity_people "
                    "(display_name, name_norm) VALUES (%s, %s) "
                    "RETURNING *",
                    (display, normalize_name(display)))
                canonical_person = cur.fetchone()
                linked_people += 1
            else:
                # Brian-pinned display names are never overwritten by
                # a resolver-chosen name.
                pinned = canonical_person.get("pinned_fields") or {}
                if isinstance(pinned, str):
                    pinned = json.loads(pinned)
                if "display_name" not in pinned:
                    pass  # keep the existing anchor name as-is
            for pid in members:
                cur.execute(
                    "UPDATE people.identity_profiles SET person_id=%s "
                    "WHERE id=%s", (canonical_person["id"], pid))
            # 100%-confident components (Brian-ruled or deterministic
            # pairs): correct + pin the canonical name, preserve the
            # misspelled variants as evidence (Brian, 2026-11-08).
            member_set = set(members)
            qualifying_pairs = [
                pair for pair, qual in pair_qualifying.items()
                if qual and pair[0] in member_set and pair[1] in member_set]
            if qualifying_pairs:
                cur.execute("SELECT * FROM people.identity_people "
                            "WHERE id=%s", (canonical_person["id"],))
                fresh_person = cur.fetchone()
                _apply_name_correction(cur, fresh_person,
                                       member_profiles, qualifying_pairs)
        breadth = recompute_breadth(cur)
        counts["breadth_people"] = len(breadth)
        conn.commit()
    finally:
        conn.close()
    print(f"resolve: {counts['pairs_considered']} candidate pairs, "
          f"{counts['same_person_written']} same-person rows written, "
          f"{counts['lookalike_written']} lookalike rows written, "
          f"{counts['below_threshold']} below threshold, "
          f"{counts['suppressed_rejected']} rejected pairs suppressed, "
          f"{linked_people} new identity_people anchors, "
          f"{counts.get('breadth_people', 0)} people with graded "
          f"multi-profile breadth")
    return counts


# --------------------------------------------------------- queue/stats

def _profile_label(profile):
    handle = profile.get("handle") or "no-handle"
    name = profile.get("display_name") or "UNKNOWN name"
    return f"{profile['platform']} @{handle} ({name})"


def show_queue():
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, display_name, profile_count, platform_count "
            "FROM people.identity_people WHERE profile_count > 0 "
            "ORDER BY profile_count DESC, platform_count DESC, "
            "display_name LIMIT 25")
        multi = cur.fetchall()
        print("MULTI-SURFACE PEOPLE — breadth = value (Brian, "
              "2026-11-08); graded links only, enrichment priority "
              "order:")
        for person in multi:
            cur.execute(
                "SELECT platform, handle FROM people.identity_profiles "
                "WHERE person_id=%s ORDER BY platform, handle",
                (person["id"],))
            surfaces = ", ".join(
                f"{r['platform']} @{r['handle'] or 'no-handle'}"
                for r in cur.fetchall())
            print(f"  {person['display_name']}: "
                  f"profile_count={person['profile_count']}, "
                  f"platform_count={person['platform_count']} — "
                  f"{surfaces}")
        if not multi:
            print("  (none yet)")
        print()
        cur.execute(
            "SELECT m.*, pa.platform AS pa_platform, pa.handle AS pa_handle,"
            " pa.display_name AS pa_name, pb.platform AS pb_platform,"
            " pb.handle AS pb_handle, pb.display_name AS pb_name "
            "FROM people.identity_matches m "
            "JOIN people.identity_profiles pa ON pa.id = m.profile_a_id "
            "JOIN people.identity_profiles pb ON pb.id = m.profile_b_id "
            "WHERE m.kind='same_person' AND m.status='pending_review' "
            "ORDER BY m.score DESC NULLS LAST, m.id")
        pending = cur.fetchall()
        print(f"PENDING REVIEW — same-person pairs for Brian "
              f"({len(pending)}):")
        for row in pending:
            signals = row["signals"]
            if isinstance(signals, str):
                signals = json.loads(signals)
            fired = signals.get("fired", {})
            evidence = ", ".join(
                f"{k}={v['value']}" for k, v in fired.items()) or "UNKNOWN"
            print(f"  [{row['id']}] score {row['score']} {row['grade']}: "
                  f"{row['pa_platform']} @{row['pa_handle']} "
                  f"({row['pa_name']}) <-> {row['pb_platform']} "
                  f"@{row['pb_handle']} ({row['pb_name']}) — {evidence}")
        cur.execute(
            "SELECT m.*, pa.platform AS pa_platform, pa.handle AS pa_handle,"
            " pa.display_name AS pa_name, pb.platform AS pb_platform,"
            " pb.handle AS pb_handle, pb.display_name AS pb_name "
            "FROM people.identity_matches m "
            "JOIN people.identity_profiles pa ON pa.id = m.profile_a_id "
            "JOIN people.identity_profiles pb ON pb.id = m.profile_b_id "
            "WHERE m.kind='lookalike_risk' ORDER BY "
            "CASE m.signals->>'verdict' WHEN 'likely_clone' THEN 0 "
            "WHEN 'unresolved' THEN 1 WHEN 'namesake' THEN 2 ELSE 3 END, "
            "m.id")
        looks = cur.fetchall()
        print(f"\nLOOKALIKE FLAGS ({len(looks)}):")
        for row in looks:
            signals = row["signals"]
            if isinstance(signals, str):
                signals = json.loads(signals)
            verdict = signals.get("verdict", "UNKNOWN")
            basis = signals.get("verdict_basis", {})
            print(f"  [{row['id']}] {verdict} ({row['status']}): "
                  f"{row['pa_platform']} @{row['pa_handle']} "
                  f"({row['pa_name']}) <-> {row['pb_platform']} "
                  f"@{row['pb_handle']} ({row['pb_name']}) — "
                  f"field_that_differs="
                  f"{basis.get('field_that_differs', 'UNKNOWN')}, "
                  f"content_sync={basis.get('content_sync', 'UNKNOWN')}")
    finally:
        conn.close()


def show_stats():
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT platform, count(*) AS n FROM "
                    "people.identity_profiles GROUP BY platform "
                    "ORDER BY platform")
        print("profiles by platform:")
        for row in cur.fetchall():
            print(f"  {row['platform']}: {row['n']}")
        cur.execute("SELECT count(*) AS n FROM people.identity_people")
        print(f"identity_people anchors: {cur.fetchone()['n']}")
        cur.execute("SELECT count(*) AS n FROM people.identity_profiles "
                    "WHERE person_id IS NOT NULL")
        print(f"profiles linked to an anchor: {cur.fetchone()['n']}")
        cur.execute("SELECT count(*) AS people, "
                    "COALESCE(max(profile_count), 0) AS max_profiles, "
                    "COALESCE(max(platform_count), 0) AS max_platforms "
                    "FROM people.identity_people WHERE profile_count >= 2")
        breadth_row = cur.fetchone()
        print(f"breadth (graded links only): {breadth_row['people']} "
              f"people with >=2 counted profiles; max "
              f"profile_count={breadth_row['max_profiles']}, max "
              f"platform_count={breadth_row['max_platforms']}")
        cur.execute("SELECT display_name, profile_count, platform_count "
                    "FROM people.identity_people WHERE profile_count > 0 "
                    "ORDER BY profile_count DESC, platform_count DESC, "
                    "display_name LIMIT 5")
        for row in cur.fetchall():
            print(f"  breadth top: {row['display_name']} — "
                  f"profile_count={row['profile_count']}, "
                  f"platform_count={row['platform_count']}")
        cur.execute("SELECT kind, grade, status, count(*) AS n FROM "
                    "people.identity_matches GROUP BY kind, grade, status "
                    "ORDER BY kind, grade, status")
        print("matches by kind / grade / status:")
        for row in cur.fetchall():
            print(f"  {row['kind']} {row['grade']} {row['status']}: "
                  f"{row['n']}")
        cur.execute("SELECT signals->>'verdict' AS verdict, count(*) AS n "
                    "FROM people.identity_matches "
                    "WHERE kind='lookalike_risk' GROUP BY verdict "
                    "ORDER BY verdict")
        print("lookalike verdicts:")
        for row in cur.fetchall():
            print(f"  {row['verdict']}: {row['n']}")
        cur.execute("SELECT count(*) AS n FROM "
                    "people.identity_bio_snapshots")
        print(f"bio snapshots: {cur.fetchone()['n']}")
        cur.execute("SELECT event_type, count(*) AS n FROM "
                    "people.identity_life_events GROUP BY event_type "
                    "ORDER BY event_type")
        events = cur.fetchall()
        print("life events by type:")
        for row in events:
            print(f"  {row['event_type']}: {row['n']}")
        if not events:
            print("  (none yet — events fire on bio CHANGE between "
                  "imports)")

        cur.execute(
            "SELECT id, platform, handle, display_name FROM "
            "people.identity_profiles WHERE handle_norm IN "
            "('zloescher1', 'zloesher1') ORDER BY platform")
        zach = cur.fetchall()
        print("\nZach Loescher case (validated 2026-11-08: SAME PERSON, "
              "owner-chosen variant confined to the FB username):")
        zach_ids = sorted(p["id"] for p in zach)
        for profile in zach:
            print(f"  {profile['platform']} @{profile['handle']} "
                  f"({profile['display_name']}) [profile {profile['id']}]")
        if len(zach_ids) == 2:
            cur.execute(
                "SELECT kind, grade, status, score, signals FROM "
                "people.identity_matches WHERE profile_a_id=%s AND "
                "profile_b_id=%s ORDER BY kind", tuple(zach_ids))
            for row in cur.fetchall():
                signals = row["signals"]
                if isinstance(signals, str):
                    signals = json.loads(signals)
                verdict = signals.get("verdict", "")
                print(f"  match {row['kind']}: grade {row['grade']}, "
                      f"status {row['status']}, score {row['score']}"
                      f"{', verdict ' + verdict if verdict else ''}")
        else:
            print("  pair not fully present in imported profiles "
                  "(UNKNOWN — not fabricated)")
    finally:
        conn.close()


# ------------------------------------------------------------ selftest

def selftest():
    checks = []

    def ck(name, ok):
        checks.append((name, bool(ok)))

    # Normalization.
    ck("platform canonicalization",
       canonical_platform("Instagram.com") == "instagram"
       and canonical_platform("twitter") == "x"
       and canonical_platform("FB") == "facebook")
    ck("handle normalization",
       normalize_handle("@ZLoescher1.") == "zloescher1"
       and normalize_handle("@@name--") == "name")
    ck("handle root strips trailing digits",
       handle_root("zloescher1") == "zloescher")
    ck("fresh levenshtein",
       levenshtein("zloescher1", "zloesher1") == 1
       and levenshtein("kitten", "sitting") == 3
       and levenshtein("", "abc") == 3)

    # Zach Loescher — the validated real outcome (2026-11-08): SAME
    # PERSON; variant confined to the FB vanity username; display
    # names correct on both sides; identical unique anchors and
    # cross-platform content sync on record from the investigation.
    zach_fb = {
        "platform": "facebook", "platform_id": "100011414759603",
        "handle": "ZLoesher1", "display_name": "Zach Loescher",
        "shared_anchors": ["sober date 2023-11-24", "retired EMS ~20y",
                           "soberpreneur.life", "Michigan"],
        "content_sync": True, "account_vintage": "facebook 1000x-era id",
        "post_count": 1200,
    }
    zach_ig = {
        "platform": "instagram", "platform_id": "17841451315998885",
        "handle": "zloescher1",
        "display_name": "Zach Loescher - Soberpreneur",
        "bio": "Father & Retired 1st Responder turned Successful "
               "Online Entrepreneur. Sober 11/24/23",
        "shared_anchors": ["sober date 2023-11-24", "retired EMS ~20y",
                           "soberpreneur.life", "Michigan"],
        "content_sync": True, "post_count": 3385,
    }
    zach_score = score_pair(zach_fb, zach_ig)
    ck("Zach variant pair scores as a same-person candidate",
       zach_score["grade"] in ("CONFIRMED", "STRONG")
       and float(zach_score["score"]) >= 0.70)
    zach_look = classify_lookalike(zach_fb, zach_ig)
    ck("Zach lookalike verdict is owner_variant (username-only variant, "
       "display names correct, anchors + content sync)",
       zach_look["verdict"] == "owner_variant"
       and zach_look["signals"]["verdict_basis"]["field_that_differs"]
       == "username_only")

    # Namesakes are the common case: same name + similar handle +
    # different world = different person, with its own outcome.
    zach_canada = {
        "platform": "instagram", "platform_id": "2001",
        "handle": "zach_loescher", "display_name": "Zach Loescher",
        "bio": "Toronto Canada hockey coach and carpenter, "
               "weekend fishing guide",
    }
    zach_pnw = {
        "platform": "facebook", "platform_id": "2002",
        "handle": "zloescher13", "display_name": "Zach Loescher",
        "bio": "Seattle Washington software engineer and "
               "trail runner, marathon training",
    }
    ck("namesake pair gets the explicit namesake outcome",
       is_lookalike_candidate(zach_canada, zach_pnw)
       and classify_lookalike(zach_canada, zach_pnw)["verdict"]
       == "namesake")

    # Content-sync slot stays UNKNOWN when no data exists — coded,
    # never fabricated.
    plain_a = {"platform": "instagram", "platform_id": "3001",
               "handle": "samhandle", "display_name": "Sam Handle"}
    plain_b = {"platform": "facebook", "platform_id": "3002",
               "handle": "samhandle2", "display_name": "Sam Handle"}
    ck("content_sync slot is UNKNOWN without data",
       classify_lookalike(plain_a, plain_b)["signals"]["verdict_basis"]
       ["content_sync"] == "UNKNOWN")

    # Anna Jo x2 — same platform, distinct ids: EXCLUDED by the
    # same-source law, mechanically.
    anna_a = {"platform": "facebook", "platform_id": "4001",
              "handle": "annajo1", "display_name": "Anna Jo"}
    anna_b = {"platform": "facebook", "platform_id": "4002",
              "handle": "annajo2", "display_name": "Anna Jo"}
    ck("Anna Jo same-platform pair is EXCLUDED by same-source law",
       score_pair(anna_a, anna_b)["grade"] == "EXCLUDED")

    # Sandy Loeven's two Instagram handles: same-source exclusion —
    # NOT auto-same; the link exists only via a Brian ruling path.
    sandy_a = {"platform": "instagram", "platform_id": "5001",
               "handle": "abundancewithsandy",
               "display_name": "Sandy Loeven"}
    sandy_b = {"platform": "instagram", "platform_id": "5002",
               "handle": "sdloeven", "display_name": "Sandy Loeven"}
    ck("Sandy two-IG-handles pair is NOT auto-same (same-source law)",
       score_pair(sandy_a, sandy_b)["grade"] == "EXCLUDED")

    # Colleague trap: same company/context, dissimilar names — the
    # conflicting-surname cap holds the pair at or below 0.35.
    colleague_a = {"platform": "linkedin", "platform_id": "6001",
                   "handle": "alexmorgan", "display_name": "Alex Morgan",
                   "bio": "Account executive at Northwind Traders",
                   "context_key": "northwind"}
    colleague_b = {"platform": "x", "platform_id": "6002",
                   "handle": "jordanlee", "display_name": "Jordan Lee",
                   "bio": "Account executive at Northwind Traders",
                   "context_key": "northwind"}
    colleague_score = score_pair(colleague_a, colleague_b)
    ck("colleague trap capped at 0.35",
       colleague_score["score"] is not None
       and float(colleague_score["score"]) <= 0.35)

    # Name-only evidence can never pass 0.65.
    name_only_a = {"platform": "instagram", "platform_id": "7001",
                   "display_name": "Pat Example"}
    name_only_b = {"platform": "threads", "platform_id": "7002",
                   "display_name": "Pat Example"}
    name_only = score_pair(name_only_a, name_only_b)
    ck("name-only pair capped at 0.65",
       name_only["score"] is not None
       and float(name_only["score"]) <= 0.65)

    # Single-token names capped at 0.50.
    single_a = {"platform": "instagram", "platform_id": "8001",
                "handle": "madonna", "display_name": "Madonna"}
    single_b = {"platform": "threads", "platform_id": "8002",
                "handle": "madonna", "display_name": "Madonna"}
    single = score_pair(single_a, single_b)
    ck("single-token name capped at 0.50 despite identical handle",
       single["score"] is not None and float(single["score"]) <= 0.50)

    # Rejected-pair memory: never re-surfaced.
    ck("rejected pair is suppressed forever",
       pair_is_suppressed({"grade": "REJECTED", "status": "auto"})
       and pair_is_suppressed({"grade": "POSSIBLE",
                               "status": "ruled_different"})
       and not pair_is_suppressed({"grade": "POSSIBLE",
                                   "status": "pending_review"})
       and not pair_is_suppressed(None))

    # Brian-pinned field protection: a conflicting overwrite is
    # refused; an unpinned field passes through.
    accepted, refused = protected_person_updates(
        {"display_name": "Sandy Loeven", "city": "Aztec"},
        {"display_name": "Sandy Smith", "city": "Denver"},
        {"display_name": "Sandy Loeven"})
    ck("pinned field overwrite refused, unpinned field accepted",
       "display_name" in refused and accepted.get("city") == "Denver"
       and "display_name" not in accepted)

    # Bio-diff life events, honestly labeled rules-v1.
    events = classify_bio_change(
        "Teacher and coach.", "Founder of NewCo — launching our app!")
    ck("bio diff classifies a life event with method rules-v1",
       events and events[0]["method"] == "rules-v1"
       and events[0]["event_type"] in ("product_launch", "job_change",
                                       "company_change"))
    ck("unchanged bio produces no life event",
       classify_bio_change("same bio", "same bio") == [])

    # Name correction (Brian, 2026-11-08): a 100%-confident
    # (Brian-ruled) pair corrects + pins the canonical name and
    # preserves the misspelling as a variant; handles are identifiers
    # and are never rewritten. An engine-only 0.90+ pair does NOT
    # qualify — a score is never 100%.
    correction = correct_canonical_name(
        "Zach Loesher",
        ["Zach Loescher", "Zach Loescher - Soberpreneur"],
        qualifying=True)
    ck("100%-confident pair: canonical name corrected + pinned, "
       "variant preserved",
       correction["display_name"] == "Zach Loescher"
       and correction["pinned"] and correction["corrected"]
       and any(v["recorded"] == "Zach Loesher"
               for v in correction["variants"]))
    handle_variants = handle_name_variants(
        [{"id": 1, "platform": "facebook", "handle": "ZLoesher1"},
         {"id": 2, "platform": "instagram", "handle": "zloescher1"}],
        "Zach Loescher")
    ck("misspelled handle recorded as variant, handle itself "
       "untouched",
       len(handle_variants) == 1
       and handle_variants[0]["recorded"] == "ZLoesher1")
    engine_only = score_pair(
        {"platform": "facebook", "platform_id": "9001",
         "handle": "ZLoesher1", "display_name": "Zach Loescher"},
        {"platform": "instagram", "platform_id": "9002",
         "handle": "zloescher1", "display_name": "Zach Loescher"})
    no_correction = correct_canonical_name(
        "Zach Loesher", ["Zach Loescher"],
        qualifying=is_100_confident(engine_only))
    ck("engine-only high score is NOT 100%: name NOT auto-corrected",
       float(engine_only["score"]) >= 0.85
       and not is_100_confident(engine_only)
       and no_correction["display_name"] == "Zach Loesher"
       and not no_correction["pinned"])
    ck("deterministic match IS 100% confident",
       is_100_confident({"signals": {"deterministic":
                                     "shared_meta_platform_id"}})
       and is_100_confident({"method": "brian",
                             "status": "ruled_same"}))

    # Breadth = value (Brian, 2026-11-08): graded links only.
    breadth_profiles = [
        {"id": 1, "person_id": 10, "platform": "facebook"},
        {"id": 2, "person_id": 10, "platform": "instagram"},
        {"id": 3, "person_id": 10, "platform": "threads"},
        {"id": 4, "person_id": 11, "platform": "facebook"},
        {"id": 5, "person_id": 12, "platform": "instagram"},
        {"id": 6, "person_id": 12, "platform": "instagram"},
    ]
    breadth_matches = [
        {"profile_a_id": 1, "profile_b_id": 2, "grade": "CONFIRMED",
         "status": "auto"},
        {"profile_a_id": 1, "profile_b_id": 3, "grade": "STRONG",
         "status": "auto"},
        {"profile_a_id": 5, "profile_b_id": 6, "grade": "POSSIBLE",
         "status": "pending_review"},
    ]
    breadth = compute_breadth(breadth_profiles, breadth_matches)
    ck("breadth: 3 confirmed profiles across 3 platforms outrank 1",
       breadth[10]["profile_count"] == 3
       and breadth[10]["platform_count"] == 3
       and person_value_rank(breadth[10]) > person_value_rank(
           breadth.get(11)))
    ck("breadth: a POSSIBLE-only second profile does NOT raise "
       "the count",
       12 not in breadth)
    sandy_breadth = compute_breadth(
        [{"id": 7, "person_id": 13, "platform": "instagram"},
         {"id": 8, "person_id": 13, "platform": "instagram"},
         {"id": 9, "person_id": 13, "platform": "facebook"}],
        [{"profile_a_id": 7, "profile_b_id": 9, "grade": "CONFIRMED",
          "status": "ruled_same"},
         {"profile_a_id": 8, "profile_b_id": 9, "grade": "CONFIRMED",
          "status": "ruled_same"}])
    ck("breadth: same-platform second handle raises profile_count "
       "but not platform_count",
       sandy_breadth[13]["profile_count"] == 3
       and sandy_breadth[13]["platform_count"] == 2)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        raise SystemExit(1)


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(
        description="SBOS Identity Resolution — graded cross-platform "
                    "identity matching with lookalike detection. "
                    "Mapping-only; nothing here contacts anyone.")
    parser.add_argument("--init-schema", action="store_true")
    parser.add_argument("--import-profiles", metavar="JSON")
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--queue", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--rule-same", nargs=2, type=int,
                        metavar=("PROFILE_A", "PROFILE_B"),
                        help="write back Brian's ruled_same ruling "
                             "for two profile ids (100% confident: "
                             "link + correct/pin canonical name)")
    parser.add_argument("--rule-different", nargs=2, type=int,
                        metavar=("PROFILE_A", "PROFILE_B"),
                        help="write back Brian's ruled_different "
                             "ruling (REJECTED, never re-surfaced)")
    args = parser.parse_args()
    if args.init_schema:
        init_schema()
    elif args.import_profiles:
        import_profiles(args.import_profiles)
    elif args.rule_same:
        apply_ruling(args.rule_same[0], args.rule_same[1], "same")
    elif args.rule_different:
        apply_ruling(args.rule_different[0], args.rule_different[1],
                     "different")
    elif args.resolve:
        resolve()
    elif args.queue:
        show_queue()
    elif args.stats:
        show_stats()
    elif args.selftest:
        selftest()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
