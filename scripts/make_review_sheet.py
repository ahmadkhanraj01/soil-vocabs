"""Make the Step 4 review sheet from dry_run_links.csv (read-only).

Usage: python scripts/make_review_sheet.py
       [--links reports/soilvoc_levels_vs_db/dry_run_links.csv]
       [--out reports/soilvoc_levels_vs_db/review_sheet.csv]

One row per link that a person must check, in the priority order from
reports/soilvoc_levels_vs_db/IMPLEMENTATION.md:

  1. reviewed=false  (ambiguous candidates, unclear inside verdicts)
  2. broader links
  3. doubtful direct matches named in PLAN.md (biomass, immissionen, inputs, filtration)
  4. pairs missing from curation/inside_keyword_review.csv

Sorted by records (most used first). Columns:
  priority, subject_id, original_label, part, link_type, soilvoc_label, soilvoc_uri,
  level, records, note, verdict_wanted   (empty = "keep or drop?")
"""
import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# direct matches PLAN.md calls doubtful — decide keep/drop
DOUBTFUL = {"biomass", "immissionen", "inputs", "filtration", "crop biomass"}
# pairs the builder could not find in the inside review
MISSING_REVIEW = {
    ("podzol soil", "https://w3id.org/eusoilvoc#PodzolsFAO"),
    ("drained histosols", "https://w3id.org/eusoilvoc#HistosolsFAO"),
    ("drained histosols", "https://w3id.org/eusoilvoc#HistosolsUSDA"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--links", default=str(ROOT / "reports/soilvoc_levels_vs_db/dry_run_links.csv"))
    ap.add_argument("--subjects", default=str(ROOT / "reports/subjects_cleaned/subjects_cleaned.csv"))
    ap.add_argument("--out", default=str(ROOT / "reports/soilvoc_levels_vs_db/review_sheet.csv"))
    args = ap.parse_args()

    with open(args.links, newline="") as f:
        links = list(csv.DictReader(f))

    out_rows = []
    for l in links:
        label = (l["original_label"] or "").strip().lower()
        if l["reviewed"] == "False":
            kind = "ambiguous candidate" if l["note"] == "ambiguous candidate" \
                else "unclear inside verdict"
            verdict = "keep (which concept?) or drop"
            prio = 1
        elif l["link_type"] == "broader":
            kind, verdict, prio = "broader link", "keep broader or drop", 2
        elif label in DOUBTFUL or (l["part"] or "").strip().lower() in DOUBTFUL:
            kind, verdict, prio = "doubtful direct match", "keep or drop", 3
        elif (l["part"], l["soilvoc_uri"]) in MISSING_REVIEW \
                or (l["original_label"], l["soilvoc_uri"]) in MISSING_REVIEW:
            kind, verdict, prio = "missing from inside review", "add verdict to review CSV", 4
        else:
            continue
        out_rows.append({
            "priority": prio, "subject_id": l["subject_id"],
            "original_label": l["original_label"], "part": l["part"],
            "link_type": l["link_type"], "soilvoc_label": l["soilvoc_label"],
            "soilvoc_uri": l["soilvoc_uri"], "level": l["level"],
            "records": int(l["records"] or 0), "note": l["note"],
            "kind": kind, "verdict_wanted": verdict, "verdict": "", "checked_by": "",
        })

    # priority 4: pairs the builder skipped because the review has no verdict
    # for them — they are in subjects_cleaned.csv but not in dry_run_links.csv
    linked = {(l["subject_id"], l["soilvoc_uri"]) for l in links}
    with open(args.subjects, newline="") as f:
        for s in csv.DictReader(f):
            if s["status"] != "soilvoc-partial":
                continue
            for uri in (u.strip() for u in (s["soilvoc_uri"] or "").split(";")):
                if (s["subject_id"], uri) in linked:
                    continue
                if (s["part"], uri) not in MISSING_REVIEW \
                        and (s["original_label"], uri) not in MISSING_REVIEW:
                    continue
                out_rows.append({
                    "priority": 4, "subject_id": s["subject_id"],
                    "original_label": s["original_label"], "part": s["part"],
                    "link_type": "inside", "soilvoc_label": s["soilvoc_label"],
                    "soilvoc_uri": uri, "level": s["soilvoc_level"],
                    "records": int(s["records"] or 0),
                    "note": "not in curation/inside_keyword_review.csv",
                    "kind": "missing from inside review",
                    "verdict_wanted": "add verdict to review CSV", "verdict": "",
                    "checked_by": "",
                })

    out_rows.sort(key=lambda r: (r["priority"], -r["records"], r["original_label"]))

    out = Path(args.out)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # summary per priority group
    groups = {}
    for r in out_rows:
        g = groups.setdefault(r["priority"], {"rows": 0, "records": set(), "kinds": set()})
        g["rows"] += 1
        g["kinds"].add(r["kind"])
    print(f"review sheet written: {out.relative_to(ROOT)} ({len(out_rows)} rows)")
    for prio in sorted(groups):
        g = groups[prio]
        print(f"  priority {prio}: {g['rows']:4} rows  ({', '.join(sorted(g['kinds']))})")
    # how many records would change if every sheet row were dropped (worst case)
    print("  (fill in the 'verdict' column, then re-run build_soilvoc_links.py "
          "with the decisions applied)")


if __name__ == "__main__":
    main()
