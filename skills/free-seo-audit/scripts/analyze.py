#!/usr/bin/env python3
"""
analyze.py - turn raw Search Console (and optional GA4) data into audit findings.

Pure standard library. Works on:
  * JSON files written by fetch.py, or
  * CSV files exported by hand from the Search Console "Performance" report
    (Queries tab / Pages tab), so the audit runs with zero setup.

Usage (JSON from fetch.py):
  python analyze.py --data-dir audit-ranksto.com --out audit-ranksto.com/findings.json

Usage (manual CSV exports):
  python analyze.py \
      --cur-queries cur_queries.csv --prev-queries prev_queries.csv \
      --cur-pages cur_pages.csv     --prev-pages prev_pages.csv \
      --out findings.json

Thresholds can be tuned with flags; run with -h to see them.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

# Typical organic CTR by rounded position (desktop+mobile blend, conservative).
# Used only to estimate "missing clicks" for CTR anomalies, never reported as fact.
EXPECTED_CTR = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.04, 7: 0.03,
                8: 0.025, 9: 0.02, 10: 0.018}


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def _num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_rows(path: str, dims: list[str]) -> list[dict]:
    """Return rows as dicts: {<dim>: str, clicks, impressions, ctr, position}."""
    if not path or not os.path.exists(path):
        return []
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("rows", data) if isinstance(data, dict) else data
        out = []
        for r in raw:
            keys = r.get("keys")
            row = {}
            if keys is not None:
                for d, k in zip(dims, keys):
                    row[d] = k
            else:
                for d in dims:
                    row[d] = r.get(d, "")
            row["clicks"] = _num(r.get("clicks"))
            row["impressions"] = _num(r.get("impressions"))
            row["ctr"] = _num(r.get("ctr"))
            row["position"] = _num(r.get("position"))
            out.append(row)
        return out

    # CSV export from the Search Console UI.
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            low = {k.strip().lower(): v for k, v in r.items() if k}
            row = {}
            first_col = next(iter(r.values())) if r else ""
            for d in dims:
                row[d] = (low.get(d) or low.get("top " + d + "s") or low.get(d + "s")
                          or low.get("top " + d) or first_col or "")
            row["clicks"] = _num(low.get("clicks"))
            row["impressions"] = _num(low.get("impressions"))
            row["ctr"] = _num(low.get("ctr"))
            row["position"] = _num(low.get("position"))
            if not row["ctr"] and row["impressions"]:
                row["ctr"] = row["clicks"] / row["impressions"]
            out.append(row)
    return out


def index_by(rows, key):
    return {r[key]: r for r in rows if r.get(key)}


def pct(a, b):
    if not b:
        return None
    return (a - b) / b


# ----------------------------------------------------------------------------
# Analysis
# ----------------------------------------------------------------------------
def totals(rows):
    c = sum(r["clicks"] for r in rows)
    i = sum(r["impressions"] for r in rows)
    pos = (sum(r["position"] * r["impressions"] for r in rows) / i) if i else 0
    return {"clicks": c, "impressions": i, "ctr": (c / i) if i else 0, "position": pos}


def baseline(cur, prev):
    t1, t0 = totals(cur), totals(prev)
    return {
        "current": t1, "previous": t0,
        "delta": {k: (t1[k] - t0[k]) for k in t1},
        "delta_pct": {k: pct(t1[k], t0[k]) for k in ("clicks", "impressions", "ctr")},
    }


def decaying_pages(cur_pages, prev_pages, min_prev_clicks=10, drop=0.30):
    cur = index_by(cur_pages, "page")
    out = []
    for page, p in index_by(prev_pages, "page").items():
        if p["clicks"] < min_prev_clicks:
            continue
        c = cur.get(page, {"clicks": 0, "impressions": 0, "position": 0, "ctr": 0})
        change = pct(c["clicks"], p["clicks"])
        if change is not None and change <= -drop:
            # Why did it fall? Separate ranking loss from demand loss from CTR loss.
            if c["impressions"] == 0:
                cause = "page disappeared from results (check indexing / redirects)"
            elif c["position"] - p["position"] >= 2:
                cause = "ranking dropped"
            elif pct(c["impressions"], p["impressions"]) is not None and \
                    pct(c["impressions"], p["impressions"]) <= -0.3:
                cause = "search demand / impressions fell"
            else:
                cause = "CTR fell (SERP change, snippet or title)"
            out.append({
                "page": page,
                "clicks_prev": p["clicks"], "clicks_cur": c["clicks"],
                "clicks_lost": p["clicks"] - c["clicks"], "change": change,
                "pos_prev": p["position"], "pos_cur": c["position"],
                "impr_prev": p["impressions"], "impr_cur": c["impressions"],
                "likely_cause": cause,
            })
    out.sort(key=lambda r: r["clicks_lost"], reverse=True)
    return out


def ctr_anomalies(cur_queries, max_pos=5.0, max_ctr=0.02, min_impr=100):
    out = []
    for q in cur_queries:
        if q["position"] and q["position"] <= max_pos and q["ctr"] < max_ctr \
                and q["impressions"] >= min_impr:
            exp = EXPECTED_CTR.get(max(1, round(q["position"])), 0.05)
            out.append({**q, "expected_ctr": exp,
                        "missing_clicks_est": max(0, q["impressions"] * exp - q["clicks"])})
    out.sort(key=lambda r: r["impressions"], reverse=True)
    return out


def striking_distance(cur_queries, lo=8.0, hi=20.0, min_impr=50):
    out = [dict(q) for q in cur_queries
           if lo <= q["position"] <= hi and q["impressions"] >= min_impr]
    for q in out:
        q["clicks_if_top3_est"] = q["impressions"] * EXPECTED_CTR[3]
    out.sort(key=lambda r: r["impressions"], reverse=True)
    return out


def cannibalization(query_page_rows, min_impr=50, min_share=0.10):
    by_q = defaultdict(list)
    for r in query_page_rows:
        by_q[r["query"]].append(r)
    out = []
    for q, rows in by_q.items():
        total_i = sum(r["impressions"] for r in rows)
        if total_i < min_impr:
            continue
        serious = [r for r in rows if r["impressions"] / total_i >= min_share]
        if len(serious) < 2:
            continue
        serious.sort(key=lambda r: (r["clicks"], r["impressions"]), reverse=True)
        out.append({
            "query": q, "impressions": total_i,
            "clicks": sum(r["clicks"] for r in rows),
            "pages": [{"page": r["page"], "clicks": r["clicks"],
                       "impressions": r["impressions"], "position": r["position"],
                       "share": r["impressions"] / total_i} for r in serious],
            "suggested_primary": serious[0]["page"],
        })
    out.sort(key=lambda r: r["impressions"], reverse=True)
    return out


def query_movers(cur_queries, prev_queries, min_impr=30):
    cur, prev = index_by(cur_queries, "query"), index_by(prev_queries, "query")
    lost = [p for k, p in prev.items() if k not in cur and p["clicks"] > 0]
    new = [c for k, c in cur.items() if k not in prev and c["impressions"] >= min_impr]
    losers, winners = [], []
    for k, c in cur.items():
        p = prev.get(k)
        if not p or max(c["impressions"], p["impressions"]) < min_impr:
            continue
        d = c["position"] - p["position"]
        row = {"query": k, "pos_prev": p["position"], "pos_cur": c["position"],
               "clicks_prev": p["clicks"], "clicks_cur": c["clicks"],
               "clicks_delta": c["clicks"] - p["clicks"]}
        if d >= 2:
            losers.append(row)
        elif d <= -2:
            winners.append(row)
    losers.sort(key=lambda r: r["clicks_delta"])
    winners.sort(key=lambda r: r["clicks_delta"], reverse=True)
    lost.sort(key=lambda r: r["clicks"], reverse=True)
    new.sort(key=lambda r: r["impressions"], reverse=True)
    return {"winners": winners, "losers": losers, "new": new, "lost": lost}


def brand_split(cur_queries, brand_terms):
    if not brand_terms:
        return None
    terms = [t.lower() for t in brand_terms]
    b = [q for q in cur_queries if any(t in q["query"].lower() for t in terms)]
    nb = [q for q in cur_queries if not any(t in q["query"].lower() for t in terms)]
    return {"brand": totals(b), "non_brand": totals(nb)}


def ga4_landing_changes(cur, prev, min_sessions=10):
    """Pages losing organic sessions or key events (revenue risk)."""
    if not cur and not prev:
        return []
    c_idx = {r["landingPage"]: r for r in cur}
    out = []
    for r in prev:
        lp = r["landingPage"]
        if r.get("sessions", 0) < min_sessions:
            continue
        c = c_idx.get(lp, {"sessions": 0, "keyEvents": 0, "totalRevenue": 0})
        s_chg = pct(c.get("sessions", 0), r.get("sessions", 0))
        k_chg = pct(c.get("keyEvents", 0), r.get("keyEvents", 0))
        if (s_chg is not None and s_chg <= -0.3) or (k_chg is not None and k_chg <= -0.3):
            out.append({"landingPage": lp,
                        "sessions_prev": r.get("sessions", 0), "sessions_cur": c.get("sessions", 0),
                        "keyEvents_prev": r.get("keyEvents", 0), "keyEvents_cur": c.get("keyEvents", 0),
                        "revenue_prev": r.get("totalRevenue", 0), "revenue_cur": c.get("totalRevenue", 0)})
    out.sort(key=lambda r: r["sessions_prev"] - r["sessions_cur"], reverse=True)
    return out


def run(args) -> dict:
    d = args.data_dir

    def pick(explicit, name):
        if explicit:
            return explicit
        if d:
            p = os.path.join(d, name)
            return p if os.path.exists(p) else None
        return None

    cur_q = load_rows(pick(args.cur_queries, "gsc_cur_query.json"), ["query"])
    prev_q = load_rows(pick(args.prev_queries, "gsc_prev_query.json"), ["query"])
    cur_p = load_rows(pick(args.cur_pages, "gsc_cur_page.json"), ["page"])
    prev_p = load_rows(pick(args.prev_pages, "gsc_prev_page.json"), ["page"])
    qp = load_rows(pick(args.query_page, "gsc_cur_query_page.json"), ["query", "page"])

    if not cur_q and not cur_p:
        sys.exit("No Search Console data found. Pass --data-dir or the --cur-* CSV/JSON files.")

    def load_json(name):
        p = os.path.join(d, name) if d else None
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return None

    ga_cur = load_json("ga4_cur_landing.json") or []
    ga_prev = load_json("ga4_prev_landing.json") or []

    findings = {
        "baseline_queries": baseline(cur_q, prev_q) if cur_q else None,
        "baseline_pages": baseline(cur_p, prev_p) if cur_p else None,
        "decaying_pages": decaying_pages(cur_p, prev_p, args.min_prev_clicks, args.drop),
        "ctr_anomalies": ctr_anomalies(cur_q, args.ctr_max_pos, args.ctr_max, args.ctr_min_impr),
        "striking_distance": striking_distance(cur_q, args.sd_lo, args.sd_hi, args.sd_min_impr),
        "cannibalization": cannibalization(qp, args.cannibal_min_impr, args.cannibal_min_share) if qp else [],
        "query_movers": query_movers(cur_q, prev_q),
        "brand_split": brand_split(cur_q, [t for t in (args.brand or "").split(",") if t.strip()]),
        "ga4_landing_losers": ga4_landing_changes(ga_cur, ga_prev),
        "ga4_ai": load_json("ga4_ai.json"),
        "notes": [],
    }
    if not qp:
        findings["notes"].append("No query+page data: cannibalization skipped "
                                 "(CSV mode cannot see it; use fetch.py or filter one query at a time in GSC).")
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir")
    ap.add_argument("--cur-queries"); ap.add_argument("--prev-queries")
    ap.add_argument("--cur-pages"); ap.add_argument("--prev-pages")
    ap.add_argument("--query-page", help="current-period query+page rows (JSON from fetch.py)")
    ap.add_argument("--brand", help="comma-separated brand terms, e.g. 'ranksto,rank sto'")
    ap.add_argument("--min-prev-clicks", type=float, default=10)
    ap.add_argument("--drop", type=float, default=0.30)
    ap.add_argument("--ctr-max-pos", type=float, default=5)
    ap.add_argument("--ctr-max", type=float, default=0.02)
    ap.add_argument("--ctr-min-impr", type=float, default=100)
    ap.add_argument("--sd-lo", type=float, default=8)
    ap.add_argument("--sd-hi", type=float, default=20)
    ap.add_argument("--sd-min-impr", type=float, default=50)
    ap.add_argument("--cannibal-min-impr", type=float, default=50)
    ap.add_argument("--cannibal-min-share", type=float, default=0.10)
    ap.add_argument("--out", default="findings.json")
    args = ap.parse_args(argv)
    findings = run(args)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)
    s = {k: (len(v) if isinstance(v, list) else None) for k, v in findings.items()}
    print(json.dumps({"written": args.out, "counts": {k: v for k, v in s.items() if v is not None}}, indent=2))


if __name__ == "__main__":
    main()
