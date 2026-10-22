"""Propose SoilVoc concepts for records without subjects, using the Mistral API.

Resumable: results are appended to <out>/results.jsonl; run the same command to continue.
Measures tokens and cost per record; progress.json feeds mistral/ui.py.
The database is only read (SELECT, read-only session).

  python mistral/extract.py --limit 100                      # 100 random records
  python mistral/extract.py --model mistral-small-latest --workers 4     # all records without subjects

Run mistral/estimate.py first to see what the full run will cost.
"""
import argparse
import csv
import json
import signal
import threading
from pathlib import Path

import common

HERE = Path(__file__).resolve().parent


def export_csv(out, concepts):
    n = 0
    with open(out / "results.jsonl", encoding="utf-8") as f, open(out / "llm_concepts.csv", "w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["record_identifier", "matched_label", "concept_uri", "concept_label", "model"])
        for line in f:
            r = json.loads(line)
            for t in r["terms"]:
                w.writerow([r["id"], t["label"], t["uri"], concepts[t["uri"]]["label"], r["model"]])
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="mistral-small-latest")
    ap.add_argument("--embed-model", default="mistral-embed")
    ap.add_argument("--limit", type=int, default=0, help="0 = all records without subjects")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=float, default=0.42, help="random order of the records, -1..1")
    ap.add_argument("--top-k", type=int, default=25)
    ap.add_argument("--max-terms", type=int, default=5)
    ap.add_argument("--out", default=str(HERE / "runs" / "extract"))
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    ctx = common.Context(a.model, a.embed_model, out, a.top_k, a.max_terms)
    allrecs = ctx.records_from_db(a.seed)
    recs = allrecs[: a.limit] if a.limit else allrecs
    print(f"{len(allrecs)} records without subjects in the database, processing {len(recs)} with {a.model}, {a.workers} workers")
    print(f"prices (USD per million tokens): input {ctx.price['input']}, output {ctx.price['output']}; see mistral/prices.json")
    if not a.yes:
        if input("This sends the titles and abstracts to the Mistral API. Start? [y/N] ").strip().lower() != "y":
            raise SystemExit("cancelled")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    cfg = {"provider": "mistral", "model": a.model, "embed_model": a.embed_model, "workers": a.workers,
           "source": "database (records without subjects)", "out": str(out), "started_at": common.now(), "kind": "extract"}
    prog, fatal = common.run_batch(ctx, recs, out, a.workers, cfg, len(allrecs), stop)
    n = export_csv(out, ctx.concepts) if (out / "results.jsonl").exists() else 0
    s = prog.s
    print(f"\n{s['done']}/{len(recs)} records, {s['errors']} errors, cost ${s['cost_usd']:.4f}, {n} rows in {out / 'llm_concepts.csv'}")
    if fatal:
        print("STOPPED:", fatal[0])


if __name__ == "__main__":
    main()
