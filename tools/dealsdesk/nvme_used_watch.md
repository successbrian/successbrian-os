# DealsDesk Watch — Used 4TB Gen4 NVMe (health >90%)

Brian's rulings, 2026-11-12:
- "we pick up outstanding deals on 4TB (>90% health) on the used market"
- "we build a NAS somewhere with used 4TB drives" (mismatched brands fine)
- "improve dealsdesk so that it finds these"

## The need (live)
- sbostasks task **18207** (hardware_need marker, staged by need_from_task)
- sbos_need_requests **243** → promoted by needs_intake
- dealsdesk.ecosystem_needs **47**: "Used 4TB Gen4 NVMe SSD (M.2 2280)",
  target_buy_price **$460**, qty_needed **5**, status open, urgency 4

## What counts as a find
ALL of these, or it is not a find:
- Used market (eBay / Facebook Marketplace / Craigslist), US seller
- 4TB, M.2 2280, PCIe Gen4 x4, TLC — models: Samsung 990 PRO,
  WD SN850X, Seagate FireCuda 530, Sabrent Rocket 4 Plus,
  Kingston KC3000, HP FX900 Pro (or equal class)
- **Health DOCUMENTED >90%** — a SMART / CrystalDiskInfo screenshot
  in the listing, or a stated health %. No evidence = not a find,
  whatever the price. (Seller-stated health without a screenshot
  is a lead: ask for the screenshot; the answer promotes it.)
- Price at or under the need's $460 target for flagship class with
  documented health. (New-price floor, verified 2026-11-12:
  flagship new $799.99, mid-tier new ~$490 — the used gate exists
  because new Gen4 4TB is too expensive.)

## Where the drives go (fill order)
1. **NAS pool** — mirrored pairs; brands may mismatch, sizes match
   within a pair (ZFS) or anything-goes (Unraid). Host/OS unruled.
2. **Alpha** — the empty second M.2 slot (K11, Gen4 x4).
3. **Bravo** — the matched Colibri pair (same model preferred:
   a striped pool runs at the slower drive, sized by the smaller).

## Machinery wired 2026-11-12
- The need above (the desk's ERP loop now works it daily:
  need_from_task 06:00 → needs_intake 06:20 → need_status_sync 07:00)
- Craigslist full scrape gained three sweeps (deployed
  /home/dealsdesk/scripts/cl_full_scrape.py, backup
  .bak-20261112-nvme): kw-nvme-4tb, kw-nvme-ssd, kw-990-pro —
  every metro in the scraper's city list, every run
- QA: project dealsdesk-nvme-watch (checks: need live, scraper armed)

## Evidence at wiring time (2026-11-12, all verified live)
- eBay: FireCuda 530 4TB $447.84 — SMART screenshot shows 100%
  health (seller mvgtech, 100%/846) — PASSES
- eBay: Sabrent Rocket 4 Plus 4TB $485 — stated 98% health with
  screenshots, 2 available (seller bzives, 100%/3.1K) — PASSES
  on health; above the $460 target (Best Offer listing)
- FB Marketplace: HP FX900 Pro 4TB $350, Burnsville MN — health
  unstated (lead; ask for screenshot)
- FB Marketplace: Samsung 990 PRO 2TB x2 $500, Lakeville MN —
  health unstated (lead; a matched pair if health proves out)
- eBay SN850X 4TB $455 (0-feedback seller, no health) and $500
  (85.7% seller, no health) — NOT finds under the gate
