# SuccessBrian OS

A self-hosted, self-funded, multi-agent operating system for running a one-person business.

## The honest origin story

I wanted an agent operating system. I tried Paperclip OS and couldn't get it to run
reliably — I kept struggling with setup and stability. So instead of giving up, I
decided to build my own. SuccessBrian OS is that system: a production multi-agent
ecosystem running on top of the [Hermes Agent](https://github.com/NousResearch/hermes-agent)
framework, which I forked and customized into something I actually use every day.

## What it runs

- 8 agents + 16 specialized workers, orchestrated end to end
- A PostgreSQL-backed knowledge architecture ("second brain") with confidence scoring,
  expiry, and verification — so the memory doesn't rot
- Real data pipelines (SEC EDGAR, search, enrichment)
- A hardware fleet sourced and financed by flipping deals

...all on roughly $500 of self-sourced hardware.

## The philosophy

The goal isn't to sell AI hype. It's to run real infrastructure that cuts costs and
keeps data private — on hardware you own. "Infrastructure Plumber," not "AI consultant."

## What's public vs. private

This repo holds the generalizable patterns: the architecture, the memory design, the
orchestration lessons. The production system, its data, and the deal-finding pipeline
live in private repos — because that part is the actual business.
