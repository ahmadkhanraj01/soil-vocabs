"""Compare every field of records that exist in both stage (DB 1) and dev (DB 2).

Read-only. Records are joined on records.identifier. Writes to reports/stage_vs_dev/:
  full_comparison.md   one table per kind: all fields including subjects, and subjects only
  field_changes.csv    one row per changed field: identifier, field, stage value, dev value

  python scripts/compare_stage_dev_fields.py
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import compare_stage_dev as base

ROOT = base.ROOT
FIELDS = ["title", "abstract", "resource_type", "license", "language", "thumbnail", "publication_date",
          "resource_creation_date", "resource_updated_date", "harvest_date", "spatial", "temporal_start",
          "temporal_end", "raw_metadata", "approval_status", "url"]
SKIP_CHANGES_CSV = {"harvest_date"}  # differs by design in almost every row; counted in the table only


def load(env, sfx):
    conn, schema, _ = base.connect(env, sfx)
    cur = conn.cursor()
    cur.execute(f"select identifier, {', '.join(FIELDS)}, id from {schema}.records")
    recs = {r[0]: dict(zip(FIELDS, r[1:-1])) | {"_id": r[-1]} for r in cur.fetchall()}
    cur.execute(f"select rs.record_id, s.label from {schema}.record_subject rs join {schema}.subjects s on s.id = rs.subject_id")
    subj = defaultdict(set)
    for rid, lab in cur.fetchall():
        if lab:
            subj[rid].add(lab)
    conn.close()
    return recs, subj


def norm(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return str(v)


def cell(v):
    return "" if v is None else v[:300].replace("\n", " ")


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def table(rows):
    out = ["| Field | Same | Changed | Filled in dev | Emptied in dev | Empty in both |", "|---|---|---|---|---|---|"]
    for name, c in rows:
        n = sum(c.values())
        out.append(f"| {name} | {c['same']:,} ({pct(c['same'], n)}) | {c['changed']:,} | {c['filled']:,} | {c['emptied']:,} | {c['empty']:,} |")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT / ".env"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "stage_vs_dev"))
    a = ap.parse_args()
    out = Path(a.out)
    env = base.cmp.load_env(a.env)
    (rs, ss), (rd, sd) = load(env, "1"), load(env, "2")
    both = sorted(set(rs) & set(rd))

    counts = {f: defaultdict(int) for f in FIELDS + ["subjects"]}
    changes = []
    for k in both:
        s, d = rs[k], rd[k]
        for f in FIELDS + ["subjects"]:
            if f == "subjects":
                x = norm("|".join(sorted(ss.get(s["_id"], ()))))
                y = norm("|".join(sorted(sd.get(d["_id"], ()))))
            else:
                x, y = norm(s[f]), norm(d[f])
            if x is None and y is None:
                kind = "empty"
            elif x == y:
                kind = "same"
            elif x is None:
                kind = "filled"
            elif y is None:
                kind = "emptied"
            else:
                kind = "changed"
            counts[f][kind] += 1
            if kind != "same" and kind != "empty" and f not in SKIP_CHANGES_CSV:
                changes.append([k, f, kind, cell(x), cell(y)])

    with open(out / "field_changes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["identifier", "field", "change", "stage_value", "dev_value"])
        w.writerows(changes)

    def filled(recs, subj, keys, f):
        if f == "subjects":
            return sum(1 for k in keys if subj.get(recs[k]["_id"]))
        return sum(1 for k in keys if norm(recs[k][f]) is not None)

    def inc_table(keys_s, keys_d):
        out_ = ["| Field | Stage | Dev | Increase / decrease |", "|---|---|---|---|"]
        for f in FIELDS + ["subjects"]:
            x, y = filled(rs, ss, keys_s, f), filled(rd, sd, keys_d, f)
            out_.append(f"| {f} | {x:,} ({pct(x, len(keys_s))}) | {y:,} ({pct(y, len(keys_d))}) | {y - x:+,} |")
        return out_

    # records with no difference at all (harvest_date ignored)
    differing = {c[0] for c in changes}
    allf = [(f, counts[f]) for f in FIELDS + ["subjects"]]
    lines = ["# Stage vs dev: full comparison of records in both", "",
             f"{len(both):,} records have the same `identifier` in stage and dev. Each field is compared "
             "after trimming whitespace; JSON is compared by content. Read-only.", "",
             "Meaning: *Changed* = both have a value and they differ; *Filled in dev* = empty in stage, value in dev; "
             "*Emptied in dev* = value in stage, empty in dev.", "",
             "## Records with a value, per field (stage, dev, increase / decrease)", "",
             f"Same {len(both):,} records in both databases:", ""]
    lines += inc_table(both, both)
    lines += ["", f"All records (stage {len(rs):,}, dev {len(rd):,}):", ""]
    lines += inc_table(list(rs), list(rd))
    lines += ["", "## All fields, including subjects (how the values differ record by record)", ""]
    lines += table(allf)
    lines += ["", f"Records with no difference in any field except `harvest_date`: {len(both) - len(differing):,} "
              f"({pct(len(both) - len(differing), len(both))}).", "",
              "## Subjects only", ""]
    lines += table([("subjects (set of labels)", counts["subjects"])])
    lines += ["", "## What the differences look like (examples from `field_changes.csv`)", "",
              "- `language`: stage stores the name (`English`, `German`), dev stores the code (`en`, `de`), so almost every row differs.",
              "- `approval_status`: stage `approved`, dev `pending` in every shared record.",
              "- `resource_type`: stage `Other`, dev `Unknown` in many records.",
              "- `raw_metadata`: differs in nearly all records because the harvested JSON contains a new `_version_` number; "
              "some records also have a different abstract or title in it.",
              "- `title`: dev often drops a scale suffix (`... 1:1.000.000`) or keeps HTML and extra whitespace from the source.",
              "- `publication_date` and `resource_updated_date`: often present in stage and empty in dev.", "",
              "See `report.md` for subject and SoilVoc totals and `common_subjects_changed.csv` for the subject differences. "
              "`field_changes.csv` lists every changed, filled or emptied field with both values (cut at 300 characters; "
              "`harvest_date` is counted above but not listed).", ""]
    (out / "full_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
