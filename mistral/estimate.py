"""Estimate the cost and time of the Mistral extraction before running it on all records.

It really calls the API for a random sample (default 500 records, cost a few cents), records tokens and
seconds per record, and reports the numbers for the first 10, 50, 100 and 500 records plus a projection
for all records without subjects.  Nothing is written to the database.

  python mistral/estimate.py                      # model mistral-small-latest, 4 workers
  python mistral/estimate.py --model ministral-8b-latest --workers 8
  python mistral/estimate.py --sizes 10,50          # smaller test first
"""
import argparse
import json
import statistics
import threading
from pathlib import Path

import common

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="mistral-small-latest")
    ap.add_argument("--embed-model", default="mistral-embed")
    ap.add_argument("--sizes", default="10,50,100,500")
    ap.add_argument("--workers", type=int, default=4, help="use the number you plan to use for the full run")
    ap.add_argument("--seed", type=float, default=0.42)
    ap.add_argument("--out", default="")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    sizes = sorted({int(x) for x in a.sizes.split(",")})
    out = Path(a.out or HERE / "runs" / f"estimate-{a.model}")
    out.mkdir(parents=True, exist_ok=True)

    ctx = common.Context(a.model, a.embed_model, out)
    allrecs = ctx.records_from_db(a.seed)
    sample = allrecs[: max(sizes)]
    target = len(allrecs)
    print(f"sample of {len(sample)} random records out of {target} without subjects; model {a.model}; {a.workers} workers")
    if not a.yes:
        if input("This sends the titles and abstracts of the sample to the Mistral API (a few cents). Start? [y/N] ").strip().lower() != "y":
            raise SystemExit("cancelled")
    cfg = {"provider": "mistral", "model": a.model, "embed_model": a.embed_model, "workers": a.workers,
           "source": "estimate sample", "out": str(out), "started_at": common.now(), "kind": "estimate"}
    prog, fatal = common.run_batch(ctx, sample, out, a.workers, cfg, target, threading.Event())

    # per-record results in the order they finished
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    ids = {r["identifier"] for r in sample}
    rows = sorted((r for r in rows if r["id"] in ids), key=lambda r: r["t"])
    table = []
    for n in sizes:
        part = rows[:n]
        if len(part) < n:
            continue
        wall = part[-1]["t"]
        cost = sum(r["cost_usd"] for r in part)
        table.append({"records": n, "seconds": round(wall, 1), "seconds_per_record": round(wall / n, 2),
                      "tokens_in": sum(r["tokens_in"] for r in part), "tokens_out": sum(r["tokens_out"] for r in part),
                      "tokens_embed": sum(r["tokens_embed"] for r in part), "cost_usd": round(cost, 5),
                      "cost_per_record_usd": round(cost / n, 6), "avg_terms": round(sum(len(r["terms"]) for r in part) / n, 2),
                      "empty": sum(1 for r in part if not r["terms"])})
    if not table:
        raise SystemExit("no sample size completed; see progress.json")
    last = table[-1]
    per_cost = [r["cost_usd"] for r in rows]
    sd = statistics.pstdev(per_cost) if len(per_cost) > 1 else 0
    se = sd / len(per_cost) ** 0.5
    proj = {"records": target, "basis_records": last["records"],
            "cost_usd": round(last["cost_per_record_usd"] * target, 2),
            "cost_usd_low": round((last["cost_per_record_usd"] - 2 * se) * target, 2),
            "cost_usd_high": round((last["cost_per_record_usd"] + 2 * se) * target, 2),
            "seconds": round(last["seconds_per_record"] * target)}
    p = common.prices()
    what_if = {}
    tin, tout, tem = last["tokens_in"] / last["records"], last["tokens_out"] / last["records"], last["tokens_embed"] / last["records"]
    for m, pr in p["models"].items():
        what_if[m] = round((tin * pr["input"] + tout * pr["output"] + tem * ctx.embed_price) / 1e6 * target, 2)
    result = {"model": a.model, "workers": a.workers, "sample": len(rows), "rate_limited": prog.stats.get("rate_limited", 0),
              "errors": prog.s["errors"], "prices": ctx.price, "embed_price": ctx.embed_price, "table": table,
              "projection": proj, "what_if_cost_usd_same_tokens": what_if, "prices_checked": p["checked"], "at": common.now()}
    (out / "estimate.json").write_text(json.dumps(result, indent=1), encoding="utf-8")

    h = lambda s: f"{int(s // 3600)} h {int(s % 3600 // 60)} min" if s >= 3600 else f"{int(s // 60)} min {int(s % 60)} s"
    md = [f"# Mistral estimate: {a.model}, {a.workers} workers", "",
          f"Sample: {len(rows)} random records without subjects. Prices: {p['checked']}", "",
          "| Records | Time | Per record | Input tokens | Output tokens | Cost (USD) | Avg terms | No term |", "|---|---|---|---|---|---|---|---|"]
    for r in table:
        md.append(f"| {r['records']} | {h(r['seconds'])} | {r['seconds_per_record']} s | {r['tokens_in']:,} | {r['tokens_out']:,} | "
                  f"{r['cost_usd']:.4f} | {r['avg_terms']} | {r['empty']} |")
    md += ["", f"## All {target:,} records (from the {last['records']}-record sample)", "",
           f"- Cost: about **${proj['cost_usd']}** (range ${proj['cost_usd_low']} to ${proj['cost_usd_high']})",
           f"- Time: about **{h(proj['seconds'])}** with {a.workers} workers",
           f"- Rate-limit replies (429) during the sample: {result['rate_limited']}; errors: {result['errors']}", "",
           "Same tokens with other models (cost only; time and quality differ):", ""]
    md += [f"- {m}: ${c}" for m, c in what_if.items()]
    (out / "estimate.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + "\n".join(md))
    if fatal:
        print("STOPPED EARLY:", fatal[0])


if __name__ == "__main__":
    main()
