# Ranksto Free SEO Audit — a Claude skill

**A complete SEO audit from your site's own Google data. Free forever: no paid connector, no subscription, no third-party estimates.**

Ask Claude *"audit my site"* and get a prioritized report built from your real Search
Console and GA4 numbers. The report covers indexation, pages losing traffic, quick wins,
keyword cannibalization, Core Web Vitals, on-page issues, AI-search traffic and a 5-step
action plan.

Built and maintained by **[Ranksto](https://ranksto.com)**, an SEO agency for teams that want rankings without the overhead.

---

## What it checks

| Area | What you get | Data source (all free) |
|---|---|---|
| **Indexation** | Sitemap URLs that never appear in search, inspected one by one: coverage state, canonical mismatches, noindex, robots | Search Console URL Inspection API + your sitemap |
| **Traffic baseline** | Clicks, impressions, CTR and position for the last 90 days vs the previous 90 | Search Console API |
| **Decaying pages** | Pages that lost more than 30% of their clicks, each with its *likely cause*: ranking drop, demand drop, CTR drop or vanished | Search Console API |
| **CTR anomalies** | Queries ranking in the top 5 with CTR under 2%, plus an estimate of the clicks you're missing and rewritten titles and meta descriptions | Search Console API |
| **Striking distance** | Queries at positions 8–20 with real impressions: one push from page 1 | Search Console API |
| **Cannibalization** | Queries where 2+ of your pages split impressions, with a suggested primary page | Search Console API (query × page) |
| **Rank movers** | Winning, losing, new and lost queries | Search Console API |
| **Brand vs non-brand** | How much of your traffic is only your brand name | Search Console API |
| **Revenue risk** | Landing pages losing organic sessions, key events or revenue, even when rankings hold | GA4 Data API |
| **AI search** | Sessions from ChatGPT, Perplexity, Gemini, Claude, Copilot…, trend, and which pages they cite | GA4 Data API |
| **AI crawler access** | Whether Googlebot, GPTBot, OAI-SearchBot, PerplexityBot, ClaudeBot and others are blocked | robots.txt |
| **Core Web Vitals** | Real-user LCP / INP / CLS (CrUX) plus a Lighthouse score | PageSpeed Insights API |
| **On-page** | Title and meta length, H1s, canonical, noindex, word count, schema, images missing alt | Page HTML |

## Three ways to feed it data (pick one)

1. **Google APIs (recommended):** a one-time, roughly 10-minute setup with your own free
   Google Cloud OAuth client. Read-only access, and the token stays on your computer.
   → [docs/SETUP.md](docs/SETUP.md)
2. **CSV export (zero setup):** export *Queries* and *Pages* from Search Console for two
   periods and hand Claude the files.
3. **Browser:** if Claude can use your browser (Claude in Chrome), it reads the reports
   straight from the Search Console and GA4 interfaces.

## Install

### Claude Code: as a plugin

```bash
/plugin marketplace add tahirniaziseo-jpg/ranksto-seo-audit
/plugin install ranksto-seo-audit@ranksto-seo-audit
```

### Claude Code: as a personal skill

```bash
git clone https://github.com/tahirniaziseo-jpg/ranksto-seo-audit.git
cp -r ranksto-seo-audit/skills/free-seo-audit ~/.claude/skills/
pip install -r ranksto-seo-audit/requirements.txt
```

### Claude.ai / Claude Desktop

Zip the `skills/free-seo-audit` folder and upload it under **Settings → Capabilities → Skills**.
The API path needs a place to run Python (Claude Code or Desktop with code execution). On
claude.ai, use CSV mode.

## Use

Just ask:

> Audit example.com

> Why is my organic traffic down?

> Find quick SEO wins for example.com

Or run the scripts yourself:

```bash
S=skills/free-seo-audit/scripts
python $S/fetch.py auth
python $S/fetch.py sites
python $S/fetch.py pull --site example.com --property 123456789 --days 90 --out audit-example.com
python $S/fetch.py sitemap-check --site example.com --out audit-example.com
python $S/analyze.py --data-dir audit-example.com --brand "example" --out audit-example.com/findings.json
python $S/fetch.py psi --url https://example.com/
```

The report ends with a **prioritized 5-item action list**, ordered by clicks at stake and
ease of the fix. Each item names the exact page and the exact change.

## Privacy

- Every Google scope is **read-only** (`webmasters.readonly`, `analytics.readonly`).
- Your data goes from Google to your computer and nowhere else.
- Revoke access any time at <https://myaccount.google.com/permissions>.

## Try it without your own data

`examples/` contains small sample CSV exports:

```bash
python skills/free-seo-audit/scripts/analyze.py \
  --cur-queries examples/cur_queries.csv --prev-queries examples/prev_queries.csv \
  --cur-pages examples/cur_pages.csv --prev-pages examples/prev_pages.csv \
  --out findings.json
```

## Need a hand?

Want an expert to read the report and fix the issues for you? **[Ranksto](https://ranksto.com)**
runs technical SEO, content and AI-search work for growing sites.
→ [ranksto.com](https://ranksto.com)

⭐ If this skill saved you a subscription, star the repo so others find it.

## License

MIT © 2026 Tahir Niazi ([Ranksto](https://ranksto.com)). See [LICENSE](LICENSE).
