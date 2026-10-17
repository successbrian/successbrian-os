#!/usr/bin/env python3
"""Seed tenant 'brian' — Brian's business core data. Idempotent."""
from core import pg_exec, lit

T = "brian"


def seed():
    pg_exec(f"INSERT INTO business_core.tenants (id, display_name, tagline) "
            f"VALUES ({lit(T)}, 'Brian Lathe', "
            f"'Income systems he owns, running on his own hardware.') "
            f"ON CONFLICT (id) DO NOTHING;")

    products = [
        ("ContactFlowCRM", "crm-core",
         "Network-marketing CRM SaaS, competes with SAGA.",
         "successbrian/contactflowcrm (PRIVATE)", "building",
         "SaaS per marketer"),
        ("Skin core", "skin-core",
         "Shared foundation all marketing skins build on.",
         None, "planned", None),
        ("TrafficStreemz", "skin",
         "Marketing skin #1: capture pages, sponsor re-assignment "
         "(future-only), marketing automation.",
         None, "building", "$30/mo"),
        ("successbrian-os", "os",
         "His operating system: agents research and propose, Brian decides.",
         "successbrian/successbrian-os (PUBLIC)", "live",
         "open source"),
    ]
    for name, layer, one_liner, repo, status, pricing in products:
        pg_exec(f"INSERT INTO business_core.products "
                f"(tenant_id, name, layer, one_liner, repo, status, pricing) "
                f"VALUES ({lit(T)}, {lit(name)}, {lit(layer)}, "
                f"{lit(one_liner)}, {lit(repo)}, {lit(status)}, "
                f"{lit(pricing)}) "
                f"ON CONFLICT (tenant_id, name) DO UPDATE SET "
                f"layer=EXCLUDED.layer, one_liner=EXCLUDED.one_liner, "
                f"repo=EXCLUDED.repo, status=EXCLUDED.status, "
                f"pricing=EXCLUDED.pricing;")

    links = [
        ("TrafficStreemz", "builds_on", "Skin core",
         "Skin #1 of many; future skins share the core."),
        ("Skin core", "builds_on", "ContactFlowCRM",
         "Skins read CRM data; the CRM never depends on a skin."),
        ("ContactFlowCRM", "competes_with", "SAGA",
         "Network-marketing recruiting system."),
        ("ContactFlowCRM", "integrates_with", "successbrian-os",
         "Standalone works; OS-connected adds Vera enrichment + PM events."),
    ]
    pg_exec(f"DELETE FROM business_core.product_links "
            f"WHERE tenant_id={lit(T)};")
    for frm, rel, to, note in links:
        pg_exec(f"INSERT INTO business_core.product_links "
                f"(tenant_id, from_product, rel, to_product, note) "
                f"VALUES ({lit(T)}, {lit(frm)}, {lit(rel)}, {lit(to)}, "
                f"{lit(note)});")

    streams = [
        ("Zilara", "mlm", "active",
         "Lead engine. Executive rank deadline Nov 1."),
        ("TikTok Shop affiliate", "affiliate", "building",
         "Fast-cash volume lane."),
        ("100-blog network", "content", "building",
         "Each blog must clear 50k monthly uniques."),
        ("Substack", "content", "active",
         "Audience home base; money-making ideas core draw."),
        ("Crypto trading + yield farming", "trading", "active",
         "Income side of the capital loop."),
        ("Realty Income (O)", "investing", "active",
         "DCA to 100 shares, then covered calls."),
        ("Forex", "trading", "active", "Carry + premium selling."),
    ]
    for name, kind, status, note in streams:
        pg_exec(f"INSERT INTO business_core.income_streams "
                f"(tenant_id, name, kind, status, note) "
                f"VALUES ({lit(T)}, {lit(name)}, {lit(kind)}, "
                f"{lit(status)}, {lit(note)}) "
                f"ON CONFLICT (tenant_id, name) DO UPDATE SET "
                f"kind=EXCLUDED.kind, status=EXCLUDED.status, "
                f"note=EXCLUDED.note;")

    flows = [
        ("Crypto trading + yield farming", "Realty Income (O)",
         "Crypto profits fund stock dip-buying."),
        ("Realty Income (O)", "Crypto trading + yield farming",
         "Stock income (dividends + premiums) funds crypto dip-buying "
         "at support."),
    ]
    pg_exec(f"DELETE FROM business_core.capital_flows "
            f"WHERE tenant_id={lit(T)};")
    for frm, to, rule in flows:
        pg_exec(f"INSERT INTO business_core.capital_flows "
                f"(tenant_id, from_stream, to_stream, rule) "
                f"VALUES ({lit(T)}, {lit(frm)}, {lit(to)}, {lit(rule)});")

    rules = [
        ("architecture",
         "people.people is the identity master. No marketing tool is ever "
         "the system of record.", "hard"),
        ("privacy",
         "Customer tenants' data NEVER touches Brian's people.people. "
         "Every sync flow is Brian's instance only.", "hard"),
        ("engineering",
         "Free-first: free is the default. Slow and working beats fast "
         "and expensive.", "hard"),
        ("engineering",
         "Systems must work with zero chat-service dependency: schedule, "
         "thinking, data, delivery live on his machines.", "hard"),
        ("money",
         "No prices in planning talk. Live verified prices only when asked, "
         "with source. Never characterize prices.", "hard"),
        ("safety",
         "Nothing destructive without Brian's go-ahead. Quarantine over "
         "delete.", "hard"),
        ("product",
         "ContactFlowCRM works standalone; OS-connected is an upgrade, "
         "never a dependency.", "hard"),
        ("product",
         "Sponsor re-assignment is future-only: new leads land right, past "
         "relationships are never rewritten.", "hard"),
    ]
    pg_exec(f"DELETE FROM business_core.rules WHERE tenant_id={lit(T)};")
    for cat, rule, sev in rules:
        pg_exec(f"INSERT INTO business_core.rules "
                f"(tenant_id, category, rule, severity) "
                f"VALUES ({lit(T)}, {lit(cat)}, {lit(rule)}, {lit(sev)});")

    tools = [
        ("FlexiFunnels", "pages + forms", "lifetime",
         "$699 lifetime, paid in full. Never re-litigate."),
        ("systeme.io", "email marketing", "monthly",
         "Email tool. Downstream of people.people, never the record."),
        ("hiro.fm", "audio nurturing", "monthly",
         "Private podcast feeds for nurture."),
        ("adilo", "video engagement", "monthly",
         "In-video CTAs + viewer analytics."),
        ("Custom blog system", "blogging", "owned",
         "His blogs run on it, not WordPress."),
    ]
    for tool, role, cost, note in tools:
        pg_exec(f"INSERT INTO business_core.tool_stack "
                f"(tenant_id, tool, role, cost_basis, note) "
                f"VALUES ({lit(T)}, {lit(tool)}, {lit(role)}, {lit(cost)}, "
                f"{lit(note)}) "
                f"ON CONFLICT (tenant_id, tool) DO UPDATE SET "
                f"role=EXCLUDED.role, cost_basis=EXCLUDED.cost_basis, "
                f"note=EXCLUDED.note;")

    people = [
        ("Brian Lathe", "human", "Decides",
         "Agents research and propose."),
        ("Meghan (CEO agent)", "agent", "CEO",
         "Financial + future planning, above Altair and Spencer."),
        ("Altair", "agent", "Sr. VP",
         "k11-alpha. Brian talks with him daily; heads-down work."),
        ("Spencer", "agent", "Senior advisor", "The synthesizer."),
        ("Gemini", "agent", "Junior advisor",
         "Closed shell — verify before trusting."),
        ("Vera", "agent", "Relationship intelligence",
         "People graph, enrichment."),
        ("DealsDesk", "agent", "Deals agent",
         "Pricing IP stays private."),
        ("Gina Acosta", "human", "Zilara build partner",
         "Brian's girlfriend; fallback inheritor."),
        ("Meghan Jean", "human", "Inheritor",
         "Brian's daughter; inherits the ecosystem."),
    ]
    for name, kind, role, note in people:
        pg_exec(f"INSERT INTO business_core.people "
                f"(tenant_id, name, kind, role, note) "
                f"VALUES ({lit(T)}, {lit(name)}, {lit(kind)}, {lit(role)}, "
                f"{lit(note)}) "
                f"ON CONFLICT (tenant_id, name) DO UPDATE SET "
                f"kind=EXCLUDED.kind, role=EXCLUDED.role, note=EXCLUDED.note;")

    roadmap = [
        ("Zilara Executive rank", "now"),
        ("ContactFlowCRM ecosystem integration (Phase 1)", "now"),
        ("FlexiFunnels bridge live (needs systeme.io API key)", "now"),
        ("100-blog network live", "next"),
        ("Skin core established", "next"),
        ("150B on own iron (MS-02 + dual B70)", "next"),
        ("successbrian-os installer for downline", "future"),
        ("EPYC-class builds", "future"),
    ]
    pg_exec(f"DELETE FROM business_core.roadmap WHERE tenant_id={lit(T)};")
    for item, horizon in roadmap:
        pg_exec(f"INSERT INTO business_core.roadmap "
                f"(tenant_id, item, horizon) "
                f"VALUES ({lit(T)}, {lit(item)}, {lit(horizon)});")

    print("seeded tenant 'brian'")


if __name__ == "__main__":
    seed()
