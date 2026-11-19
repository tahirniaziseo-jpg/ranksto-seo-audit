#!/usr/bin/env python3
"""
fetch.py - pull a site's OWN data straight from Google's free APIs.

No paid service in between. You authorise once with your own Google account;
the token stays on your computer.

APIs used (all free):
  * Search Console API      - search analytics, URL inspection, sitemaps
  * Google Analytics Data API (GA4) - organic landing pages, AI referrals
  * Google Analytics Admin API      - list your GA4 properties
  * PageSpeed Insights API  - Lighthouse + Chrome UX Report (Core Web Vitals)

Install:
  pip install google-api-python-client google-auth-oauthlib

Commands:
  python fetch.py auth                          # one-time browser sign-in
  python fetch.py sites                         # list Search Console properties
  python fetch.py ga4-properties                # list GA4 properties
  python fetch.py pull --site sc-domain:example.com [--property 123456789] [--days 90] --out audit-example
  python fetch.py inspect --site sc-domain:example.com --url https://example.com/page
  python fetch.py onpage --url https://example.com/page
  python fetch.py psi --url https://example.com/ [--strategy mobile]
  python fetch.py sitemap-check --site sc-domain:example.com --out audit-example [--limit 50]

Setup guide: docs/SETUP.md in the repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]
CONFIG_DIR = os.environ.get(
    "FREE_SEO_AUDIT_HOME",
    os.path.join(os.path.expanduser("~"), ".config", "free-seo-audit"),
)
CLIENT_SECRET = os.path.join(CONFIG_DIR, "client_secret.json")
TOKEN = os.path.join(CONFIG_DIR, "token.json")
UA = "free-seo-audit/1.0 (+https://github.com)"

AI_SOURCES = (
    "chatgpt.com|chat.openai.com|openai.com|perplexity.ai|gemini.google.com|bard.google.com|"
    "claude.ai|anthropic.com|copilot.microsoft.com|edgeservices.bing.com|you.com|phind.com|"
    "chat.deepseek.com|deepseek.com|meta.ai|grok.com|x.ai|mistral.ai|chat.mistral.ai|poe.com"
)


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------
def _need_libs():
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
    except ImportError:
        sys.exit("Missing libraries. Run:  pip install google-api-python-client google-auth-oauthlib")


def credentials(interactive=True):
    _need_libs()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds)
            return creds
        except Exception:
            creds = None  # refresh token expired (7-day limit in "Testing" mode) -> re-auth
    if not interactive:
        sys.exit("Not signed in. Run:  python fetch.py auth")
    if not os.path.exists(CLIENT_SECRET):
        sys.exit(f"OAuth client file not found at {CLIENT_SECRET}\n"
                 "Create a free Desktop OAuth client in Google Cloud and save it there. See docs/SETUP.md.")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    _save(creds)
    return creds


def _save(creds):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def svc(name, version):
    from googleapiclient.discovery import build
    return build(name, version, credentials=credentials(interactive=False), cache_discovery=False)


# ----------------------------------------------------------------------------
# Search Console
# ----------------------------------------------------------------------------
def gsc_sites():
    res = svc("searchconsole", "v1").sites().list().execute()
    return res.get("siteEntry", [])


def resolve_site(site: str) -> str:
    """Accept 'example.com' and map it to the property the user actually has."""
    if site.startswith(("sc-domain:", "http://", "https://")):
        return site
    bare = site.lower().strip("/")
    entries = [e["siteUrl"] for e in gsc_sites()]
    for cand in (f"sc-domain:{bare}", f"https://{bare}/", f"https://www.{bare}/",
                 f"http://{bare}/", f"http://www.{bare}/"):
        if cand in entries:
            return cand
    sys.exit(f"No Search Console property matches '{site}'. Available: {entries}")


def gsc_query(site, start, end, dims, row_limit=25000, max_rows=100000, search_type="web"):
    s = svc("searchconsole", "v1")
    rows, start_row = [], 0
    while True:
        body = {"startDate": start, "endDate": end, "dimensions": dims,
                "rowLimit": row_limit, "startRow": start_row, "type": search_type,
                "dataState": "final"}
        res = s.searchanalytics().query(siteUrl=site, body=body).execute()
        batch = res.get("rows", [])
        rows.extend(batch)
        if len(batch) < row_limit or len(rows) >= max_rows:
            break
        start_row += row_limit
    return rows


def gsc_inspect(site, url):
    body = {"inspectionUrl": url, "siteUrl": site}
    res = svc("searchconsole", "v1").urlInspection().index().inspect(body=body).execute()
    r = res.get("inspectionResult", {}).get("indexStatusResult", {})
    return {
        "url": url,
        "verdict": r.get("verdict"),
        "coverageState": r.get("coverageState"),
        "indexingState": r.get("indexingState"),
        "robotsTxtState": r.get("robotsTxtState"),
        "pageFetchState": r.get("pageFetchState"),
        "googleCanonical": r.get("googleCanonical"),
        "userCanonical": r.get("userCanonical"),
        "canonicalMismatch": bool(r.get("googleCanonical") and r.get("userCanonical")
                                  and r.get("googleCanonical") != r.get("userCanonical")),
        "lastCrawlTime": r.get("lastCrawlTime"),
        "crawledAs": r.get("crawledAs"),
        "sitemap": r.get("sitemap"),
        "mobileUsability": res.get("inspectionResult", {}).get("mobileUsabilityResult", {}).get("verdict"),
        "richResults": res.get("inspectionResult", {}).get("richResultsResult", {}).get("verdict"),
    }


def gsc_sitemaps(site):
    res = svc("searchconsole", "v1").sitemaps().list(siteUrl=site).execute()
    return res.get("sitemap", [])


# ----------------------------------------------------------------------------
# GA4
# ----------------------------------------------------------------------------
def ga4_properties():
    res = svc("analyticsadmin", "v1beta").accountSummaries().list(pageSize=200).execute()
    out = []
    for acc in res.get("accountSummaries", []):
        for p in acc.get("propertySummaries", []):
            out.append({"account": acc.get("displayName"),
                        "property": p["property"].split("/")[-1],
                        "name": p.get("displayName")})
    return out


def _ga4_report(prop, body):
    data = svc("analyticsdata", "v1beta")
    try:
        return data.properties().runReport(property=f"properties/{prop}", body=body).execute()
    except Exception as e:
        # Older properties: "keyEvents" may be unavailable -> fall back to "conversions".
        if "keyEvents" in json.dumps(body) and "keyEvents" in str(e):
            body = json.loads(json.dumps(body).replace("keyEvents", "conversions"))
            res = data.properties().runReport(property=f"properties/{prop}", body=body).execute()
            for h in res.get("metricHeaders", []):
                if h.get("name") == "conversions":
                    h["name"] = "keyEvents"
            return res
        raise


def _rows(res):
    dims = [h["name"] for h in res.get("dimensionHeaders", [])]
    mets = [h["name"] for h in res.get("metricHeaders", [])]
    out = []
    for r in res.get("rows", []):
        row = {d: v["value"] for d, v in zip(dims, r.get("dimensionValues", []))}
        for m, v in zip(mets, r.get("metricValues", [])):
            try:
                row[m] = float(v["value"])
            except ValueError:
                row[m] = v["value"]
        out.append(row)
    return out


def ga4_organic_landing(prop, start, end, limit=1000):
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "landingPage"}],
        "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                    {"name": "keyEvents"}, {"name": "totalRevenue"}],
        "dimensionFilter": {"filter": {"fieldName": "sessionDefaultChannelGroup",
                                       "stringFilter": {"value": "Organic Search"}}},
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": limit,
    }
    return _rows(_ga4_report(prop, body))


def ga4_ai_referrals(prop, cur, prev):
    """AI engine traffic for current vs previous period, by source and landing page."""
    flt = {"filter": {"fieldName": "sessionSource",
                      "stringFilter": {"matchType": "FULL_REGEXP",
                                       "value": f".*({AI_SOURCES}).*"}}}
    by_source = _ga4_report(prop, {
        "dateRanges": [{"startDate": cur[0], "endDate": cur[1], "name": "current"},
                       {"startDate": prev[0], "endDate": prev[1], "name": "previous"}],
        "dimensions": [{"name": "sessionSource"}],
        "metrics": [{"name": "sessions"}, {"name": "engagedSessions"}, {"name": "keyEvents"}],
        "dimensionFilter": flt, "limit": 100,
    })
    by_page = _ga4_report(prop, {
        "dateRanges": [{"startDate": cur[0], "endDate": cur[1]}],
        "dimensions": [{"name": "landingPage"}, {"name": "sessionSource"}],
        "metrics": [{"name": "sessions"}, {"name": "keyEvents"}],
        "dimensionFilter": flt,
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}], "limit": 50,
    })
    total = _ga4_report(prop, {
        "dateRanges": [{"startDate": cur[0], "endDate": cur[1]}],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
        "metrics": [{"name": "sessions"}], "limit": 50,
    })
    return {"by_source": _rows(by_source), "by_page": _rows(by_page),
            "channels": _rows(total)}


# ----------------------------------------------------------------------------
# Public (no-auth) checks: PageSpeed / CrUX, on-page, robots, sitemaps
# ----------------------------------------------------------------------------
def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


def psi(url, strategy="mobile"):
    q = {"url": url, "strategy": strategy, "category": "performance"}
    key = os.environ.get("PAGESPEED_API_KEY")
    if key:
        q["key"] = key
    api = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + urllib.parse.urlencode(q)
    try:
        _, _, body = http_get(api, timeout=120)
    except urllib.error.HTTPError as e:
        hint = ("Google rate-limits anonymous PageSpeed calls. Create a free API key "
                "(docs/SETUP.md, step 6) and set PAGESPEED_API_KEY." if e.code == 429 and not key else "")
        return {"url": url, "strategy": strategy, "error": f"HTTP {e.code}", "hint": hint}
    d = json.loads(body)
    lh = d.get("lighthouseResult", {})
    audits = lh.get("audits", {})
    field = d.get("loadingExperience", {}).get("metrics", {})
    origin = d.get("originLoadingExperience", {}).get("metrics", {})

    def f(m, k):
        v = m.get(k, {})
        return {"p75": v.get("percentile"), "category": v.get("category")} if v else None

    return {
        "url": url, "strategy": strategy,
        "lab_score": round((lh.get("categories", {}).get("performance", {}).get("score") or 0) * 100),
        "lab": {k: audits.get(k, {}).get("displayValue") for k in
                ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time",
                 "first-contentful-paint", "speed-index")},
        "field_url": {"LCP": f(field, "LARGEST_CONTENTFUL_PAINT_MS"),
                      "INP": f(field, "INTERACTION_TO_NEXT_PAINT"),
                      "CLS": f(field, "CUMULATIVE_LAYOUT_SHIFT_SCORE")},
        "field_origin": {"LCP": f(origin, "LARGEST_CONTENTFUL_PAINT_MS"),
                         "INP": f(origin, "INTERACTION_TO_NEXT_PAINT"),
                         "CLS": f(origin, "CUMULATIVE_LAYOUT_SHIFT_SCORE")},
    }


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.desc, self.canonical, self.robots = "", None, None, None
        self.h1, self.in_title, self.in_h1, self.text = [], False, False, []
        self.schema_types, self.in_ld, self.ld_buf, self.imgs_no_alt = [], False, "", 0
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            n = a.get("name", "").lower()
            if n == "description":
                self.desc = a.get("content", "")
            elif n == "robots":
                self.robots = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href")
        elif tag == "h1":
            self.in_h1 = True
            self.h1.append("")
        elif tag == "img" and not a.get("alt"):
            self.imgs_no_alt += 1
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self.in_ld, self.ld_buf = True, ""
        elif tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False
        elif tag == "script" and self.in_ld:
            self.in_ld = False
            self.schema_types += re.findall(r'"@type"\s*:\s*"([^"]+)"', self.ld_buf)
        elif tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_h1 and self.h1:
            self.h1[-1] += data
        if self.in_ld:
            self.ld_buf += data
        elif not self._skip:
            self.text.append(data)


def onpage(url):
    try:
        status, final, html = http_get(url)
    except Exception as e:
        return {"url": url, "error": str(e)}
    p = _Meta()
    p.feed(html)
    words = len(re.findall(r"\w+", " ".join(p.text)))
    title = re.sub(r"\s+", " ", p.title).strip()
    issues = []
    if not title:
        issues.append("missing <title>")
    elif len(title) > 60:
        issues.append(f"title long ({len(title)} chars, may truncate)")
    elif len(title) < 25:
        issues.append(f"title short ({len(title)} chars)")
    if not p.desc:
        issues.append("missing meta description")
    elif len(p.desc) > 160:
        issues.append(f"meta description long ({len(p.desc)} chars)")
    if len(p.h1) != 1:
        issues.append(f"{len(p.h1)} H1 tags")
    if p.robots and "noindex" in p.robots.lower():
        issues.append("meta robots NOINDEX")
    if p.canonical and p.canonical.rstrip("/") != final.rstrip("/"):
        issues.append(f"canonical points elsewhere: {p.canonical}")
    if words < 300:
        issues.append(f"thin content (~{words} words)")
    if p.imgs_no_alt:
        issues.append(f"{p.imgs_no_alt} images without alt")
    return {"url": url, "status": status, "final_url": final, "title": title,
            "title_len": len(title), "meta_description": p.desc, "h1": [h.strip() for h in p.h1],
            "canonical": p.canonical, "meta_robots": p.robots, "word_count": words,
            "schema_types": sorted(set(p.schema_types)), "issues": issues}


def sitemap_urls(sitemap_url, limit=5000, _depth=0):
    try:
        _, _, body = http_get(sitemap_url)
        root = ET.fromstring(body.encode("utf-8"))
    except Exception:
        return []
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls = []
    if root.tag.endswith("sitemapindex") and _depth < 2:
        for loc in root.iter(ns + "loc"):
            urls += sitemap_urls(loc.text.strip(), limit - len(urls), _depth + 1)
            if len(urls) >= limit:
                break
    else:
        urls = [loc.text.strip() for loc in root.iter(ns + "loc")]
    return urls[:limit]


def robots_check(origin):
    try:
        status, _, body = http_get(origin.rstrip("/") + "/robots.txt")
    except Exception as e:
        return {"error": str(e)}
    bots = ["Googlebot", "Bingbot", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
            "ClaudeBot", "Claude-SearchBot", "Google-Extended", "CCBot"]
    # Group consecutive User-agent lines; rules that follow apply to that group.
    groups, agents, in_rules = {}, [], False
    for line in body.splitlines():
        line = line.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        k = k.lower()
        if k == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(v.lower())
            for ag in agents:
                groups.setdefault(ag, {"disallow_all": False, "allow_root": False})
        elif k in ("disallow", "allow"):
            in_rules = True
            for ag in agents:
                if k == "disallow" and v == "/":
                    groups[ag]["disallow_all"] = True
                if k == "allow" and v == "/":
                    groups[ag]["allow_root"] = True

    def blocked(bot):
        g = groups.get(bot.lower()) or groups.get("*")
        return bool(g and g["disallow_all"] and not g["allow_root"])

    sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", body)
    return {"status": status, "sitemaps": sitemaps,
            "blocked_bots": [b for b in bots if blocked(b)],
            "allowed_bots": [b for b in bots if not blocked(b)]}


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------
def periods(days, lag=3):
    end = dt.date.today() - dt.timedelta(days=lag)
    start = end - dt.timedelta(days=days - 1)
    pend = start - dt.timedelta(days=1)
    pstart = pend - dt.timedelta(days=days - 1)
    f = lambda d: d.isoformat()  # noqa: E731
    return (f(start), f(end)), (f(pstart), f(pend))


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    print(f"  wrote {path}")


def cmd_pull(a):
    site = resolve_site(a.site)
    cur, prev = periods(a.days)
    os.makedirs(a.out, exist_ok=True)
    meta = {"site": site, "current": cur, "previous": prev, "days": a.days,
            "pulled_at": dt.datetime.now().isoformat(timespec="seconds")}
    print(f"Site {site}\n  current  {cur[0]} -> {cur[1]}\n  previous {prev[0]} -> {prev[1]}")
    for label, (s, e) in (("cur", cur), ("prev", prev)):
        for dims in (["query"], ["page"]):
            dump(os.path.join(a.out, f"gsc_{label}_{'_'.join(dims)}.json"),
                 {"rows": gsc_query(site, s, e, dims)})
    dump(os.path.join(a.out, "gsc_cur_query_page.json"),
         {"rows": gsc_query(site, cur[0], cur[1], ["query", "page"])})
    dump(os.path.join(a.out, "gsc_cur_device.json"),
         {"rows": gsc_query(site, cur[0], cur[1], ["device"])})
    dump(os.path.join(a.out, "gsc_cur_country.json"),
         {"rows": gsc_query(site, cur[0], cur[1], ["country"], row_limit=50, max_rows=50)})
    try:
        dump(os.path.join(a.out, "gsc_sitemaps.json"), gsc_sitemaps(site))
    except Exception as e:
        print(f"  sitemaps skipped: {e}")
    if a.property:
        try:
            dump(os.path.join(a.out, "ga4_cur_landing.json"), ga4_organic_landing(a.property, *cur))
            dump(os.path.join(a.out, "ga4_prev_landing.json"), ga4_organic_landing(a.property, *prev))
            dump(os.path.join(a.out, "ga4_ai.json"), ga4_ai_referrals(a.property, cur, prev))
        except Exception as e:
            print(f"  GA4 skipped: {e}")
            meta["ga4_error"] = str(e)
    origin = ("https://" + site.split(":", 1)[1]) if site.startswith("sc-domain:") else site
    dump(os.path.join(a.out, "robots.json"), robots_check(origin))
    meta["origin"] = origin
    dump(os.path.join(a.out, "meta.json"), meta)


def cmd_sitemap_check(a):
    """Free indexation check: sitemap URLs with zero impressions -> URL Inspection."""
    site = resolve_site(a.site)
    out = a.out
    pages_file = os.path.join(out, "gsc_cur_page.json")
    seen = set()
    if os.path.exists(pages_file):
        with open(pages_file, encoding="utf-8") as f:
            seen = {r["keys"][0].rstrip("/") for r in json.load(f).get("rows", [])}
    sm = []
    for s in gsc_sitemaps(site):
        sm += sitemap_urls(s["path"])
    if not sm:
        origin = ("https://" + site.split(":", 1)[1]) if site.startswith("sc-domain:") else site
        sm = sitemap_urls(origin.rstrip("/") + "/sitemap.xml")
    sm = list(dict.fromkeys(sm))
    silent = [u for u in sm if u.rstrip("/") not in seen]
    print(f"  sitemap URLs: {len(sm)}  | with zero impressions: {len(silent)}")
    results = []
    for u in silent[: a.limit]:
        try:
            results.append(gsc_inspect(site, u))
        except Exception as e:
            results.append({"url": u, "error": str(e)})
    summary = {}
    for r in results:
        k = r.get("coverageState") or r.get("error", "error")[:60]
        summary[k] = summary.get(k, 0) + 1
    dump(os.path.join(out, "indexation.json"),
         {"sitemap_url_count": len(sm), "zero_impression_count": len(silent),
          "inspected": len(results), "coverage_summary": summary, "results": results})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("auth")
    sp.add_parser("sites")
    sp.add_parser("ga4-properties")
    p = sp.add_parser("pull")
    p.add_argument("--site", required=True); p.add_argument("--property")
    p.add_argument("--days", type=int, default=90); p.add_argument("--out", required=True)
    p = sp.add_parser("inspect"); p.add_argument("--site", required=True); p.add_argument("--url", required=True, nargs="+")
    p = sp.add_parser("onpage"); p.add_argument("--url", required=True, nargs="+")
    p = sp.add_parser("psi"); p.add_argument("--url", required=True, nargs="+")
    p.add_argument("--strategy", default="mobile", choices=["mobile", "desktop"])
    p = sp.add_parser("robots"); p.add_argument("--origin", required=True)
    p = sp.add_parser("sitemap-check"); p.add_argument("--site", required=True)
    p.add_argument("--out", required=True); p.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)

    if a.cmd == "auth":
        credentials(interactive=True)
        print(f"Signed in. Token saved to {TOKEN}")
    elif a.cmd == "sites":
        print(json.dumps(gsc_sites(), indent=2))
    elif a.cmd == "ga4-properties":
        print(json.dumps(ga4_properties(), indent=2))
    elif a.cmd == "pull":
        cmd_pull(a)
    elif a.cmd == "inspect":
        site = resolve_site(a.site)
        print(json.dumps([gsc_inspect(site, u) for u in a.url], indent=2))
    elif a.cmd == "onpage":
        print(json.dumps([onpage(u) for u in a.url], indent=2))
    elif a.cmd == "psi":
        print(json.dumps([psi(u, a.strategy) for u in a.url], indent=2))
    elif a.cmd == "robots":
        print(json.dumps(robots_check(a.origin), indent=2))
    elif a.cmd == "sitemap-check":
        cmd_sitemap_check(a)


if __name__ == "__main__":
    main()
