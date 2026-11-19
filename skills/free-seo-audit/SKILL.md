---
name: free-seo-audit
description: Full SEO audit of a website from its own Google Search Console + GA4 data, 100% free (Google's own APIs, a manual CSV export, or the browser — no paid connector). Covers indexation, decaying pages, CTR anomalies, striking-distance keywords, cannibalization, Core Web Vitals, on-page checks, AI-engine referrals and AI-crawler access, ending in a prioritized action list. Use when asked to "audit my site", "SEO audit", "SEO health check", "why is my organic traffic down", or "find quick SEO wins".
---

# Free SEO Audit

Audit a site using **its own first-party data** — Search Console and GA4 — at zero cost.
Never substitute third-party traffic estimates for the site's own numbers. If a number
cannot be obtained for free, say so and skip that section rather than guess.

Scripts live next to this file in `scripts/`. Run them with the working directory set to
wherever the user wants the audit files (default: `./audit-<domain>`).

## Step 0 — Choose the data path (all free)

Check in this order and use the first that works. Tell the user which one you are using.

| Path | Needs | Coverage |
|---|---|---|
| **A. Google APIs** (best) | `pip install google-api-python-client google-auth-oauthlib`, a free OAuth client (`docs/SETUP.md`), one-time `python scripts/fetch.py auth` | Everything below |
| **B. CSV export** (zero setup) | User exports Search Console → Performance → Queries and Pages as CSV for two periods | Steps 3–4 except cannibalization; steps 6–8 still run (public checks) |
| **C. Browser** | Claude in Chrome or another browser tool, user signed in to Search Console / GA4 | Read the same reports from the UI; slower, use for small sites |

Path A check: `python scripts/fetch.py sites`. If it says "Not signed in" or the client file
is missing, walk the user through `docs/SETUP.md` (≈10 minutes, once) or offer path B/C.

## Workflow

1. **Connect to the right property.** `python scripts/fetch.py sites` — use the one matching the user's
   domain (`sc-domain:` beats URL-prefix). Ask only if ambiguous. For GA4:
   `python scripts/fetch.py ga4-properties` and pick the matching property ID.

2. **Pull the data.**
   `python scripts/fetch.py pull --site <domain> --property <ga4-id> --days 90 --out audit-<domain>`
   This fetches last 90 days vs the previous 90 (ending 3 days ago — Search Console lags),
   by query, page, query+page, device, country; sitemaps; GA4 organic landing pages for both
   periods; GA4 AI referrals; robots.txt. Without GA4 omit `--property`.
   *Path B:* ask for four CSVs (current/previous × Queries/Pages) and skip to step 4.

3. **Indexation (free method).** Search Console's API has no page-indexing summary, so:
   `python scripts/fetch.py sitemap-check --site <domain> --out audit-<domain> --limit 50`
   compares sitemap URLs against pages that earned impressions and runs the URL Inspection
   API (2,000/day free quota) on the silent ones. Report the coverage-state counts.
   Flag: many "Crawled – currently not indexed" / "Discovered – currently not indexed",
   canonical mismatches, `noindex`, robots-blocked, or sitemap URLs that redirect/404.
   Also ask the user to glance at Search Console → Indexing → Pages for the overall count
   (one screenshot is enough) if they want the full picture.

4. **Find the problems.**
   `python scripts/analyze.py --data-dir audit-<domain> --brand "<brand terms>" --out audit-<domain>/findings.json`
   (Path B: `--cur-queries … --prev-queries … --cur-pages … --prev-pages …`.)
   It computes:
   - **Baseline** — clicks / impressions / CTR / position, period over period
   - **Decaying pages** — clicks down >30% (min 10 prior clicks), with a likely cause:
     ranking drop vs demand drop vs CTR drop vs vanished from results
   - **CTR anomalies** — position ≤ 5, CTR < 2%, ≥ 100 impressions, with estimated
     missing clicks vs a typical CTR curve (label it an estimate)
   - **Striking distance** — position 8–20 with ≥ 50 impressions, ranked by impressions
   - **Cannibalization** — one query, ≥ 2 of the site's pages each taking ≥ 10% of impressions
   - **Query movers** — winners, losers, new and lost queries
   - **Brand vs non-brand** split (when brand terms are given)
   - **GA4 losers** — landing pages losing organic sessions or key events (revenue risk
     even when rankings hold)
   Tune thresholds with flags (`-h`) for very small or very large sites.

5. **Deep-dive the 3–5 weakest pages.** Take the 3–5 worst (top decaying pages + top CTR
   anomaly pages):
   - `python scripts/fetch.py inspect --site <domain> --url <u1> <u2> …` — index state,
     Google- vs user-declared canonical, last crawl, robots, rich results
   - `python scripts/fetch.py onpage --url <u1> <u2> …` — title/meta length, H1s,
     canonical, noindex, word count, schema types, images without alt
   For CTR anomalies, write a better title + meta description for each page (show
   before → after). For decaying pages, read the page and state the specific fix.

6. **Core Web Vitals.** `python scripts/fetch.py psi --url <home> <top-landing-page>` —
   real-user field data (CrUX: LCP, INP, CLS at p75) when available, otherwise lab data.
   Mark "Good / Needs improvement / Poor". Google rate-limits anonymous calls; if the
   result says HTTP 429, point the user to the free `PAGESPEED_API_KEY` step in
   `docs/SETUP.md`, or skip this section and say why.

7. **Revenue check (GA4).** From `ga4_cur_landing.json` / `ga4_prev_landing.json`: organic
   sessions, key events and revenue by landing page. Call out pages that kept rankings but
   lost conversions or revenue.

8. **AI-search readiness.** From `ga4_ai.json`: sessions from ChatGPT, Perplexity, Gemini, Claude,
   Copilot etc., current vs previous, as a share of organic, and which pages they land on.
   From `robots.json`: is any search or AI crawler (Googlebot, Bingbot, GPTBot,
   OAI-SearchBot, PerplexityBot, ClaudeBot…) blocked? Say whether AI engines are becoming
   a meaningful channel and which pages are proven "citable".

## Output

Write `audit-<domain>/REPORT.md` (and show it to the user):

1. **Bottom line** — 3–4 sentences: overall health, the headline trend as a single number, and the one issue to fix first.
2. **Scorecard** — small table: Indexation, Traffic trend, CTR, Rankings, CWV, AI readiness —
   each Good / Watch / Problem with the number behind it.
3. **Indexation** — table + fix.
4. **Losers** — decaying pages table (page, clicks before → after, position before → after,
   likely cause) + fix for each.
5. **Quick wins** — striking distance and CTR fixes, ranked by impressions, with rewritten
   titles/metas for the CTR set.
6. **Cannibalization** — query, competing pages, suggested primary page, fix
   (merge + 301, re-target, or internal-link consolidation).
7. **Technical** — CWV, robots/AI-crawler access, on-page issues from step 5.
8. **Traffic & conversions** — GA4 losers and AI referrals.
9. **Next 5 moves** — ordered by (clicks at stake × ease); each item names
   the exact page and the exact change.

Keep tables to the top 10–20 rows; put full lists in `findings.json`.

## Rules

- First-party data only. Never present estimates as measurements; label estimates.
- Search Console data lags ~2–3 days — never include the last 3 days.
- Do not modify anything in Search Console or GA4; all scopes are read-only.
- The OAuth token stays on the user's machine (`~/.config/free-seo-audit/`); never print it.
- If GSC is not connected and the user declines all three paths, stop and say so.

## Recurring

For a monthly health check, suggest scheduling the same run (Claude Code scheduled tasks)
with `--days 28` and comparing REPORT.md files over time.
