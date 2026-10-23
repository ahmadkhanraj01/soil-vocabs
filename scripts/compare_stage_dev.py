"""Compare the subjects of two SoilWise databases (stage = DB 1, dev = DB 2).

Read-only: SELECTs only, writes CSV/Markdown to --out. Nothing is written to a database.

1. Checks that the tables records / subjects / record_subject have the same columns in both.
2. Joins the records on records.identifier: only in dev (the fresh data), only in stage, in both.
3. For every record: does it have subjects, and are any of them SoilVoc concepts.
   SoilVoc matching reuses scripts/compare_subjects_to_soilvoc.py (exact, mapped, variant,
   normalised, and the human decisions in curation/keyword_decisions.csv).
   Suggestion-only tiers (translated_*) are not counted.

  python scripts/compare_stage_dev.py
"""
import argparse
import csv
import importlib.util
import runpy
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cmp", ROOT / "scripts" / "compare_subjects_to_soilvoc.py")
cmp = importlib.util.module_from_spec(spec)
sys.modules["cmp"] = cmp
spec.loader.exec_module(cmp)

TABLES = ("records", "subjects", "record_subject")


def connect(env, sfx):
    schema = env.get("DB_SCHEMA" + sfx, "public")
    if not cmp.re.fullmatch(r"\w+", schema):
        raise SystemExit("bad schema name")
    conn = psycopg2.connect(
        host=env["DB_HOST" + sfx], port=env["DB_PORT" + sfx], dbname=env["DB_NAME" + sfx],
        user=env["DB_USER" + sfx], password=env["DB_PASSWORD" + sfx], connect_timeout=10,
    )
    conn.set_session(readonly=True)
    return conn, schema, env["DB_NAME" + sfx]


def fetch(env, sfx):
    conn, schema, name = connect(env, sfx)
    cur = conn.cursor()
    cur.execute(
        "select table_name, column_name, data_type from information_schema.columns "
        "where table_schema = %s and table_name = any(%s) order by 1, ordinal_position",
        (schema, list(TABLES)),
    )
    columns = cur.fetchall()
    cur.execute(f"select id, identifier, title, harvest_date, created_at from {schema}.records")
    records = cur.fetchall()
    cur.execute(
        f"select rs.record_id, s.label from {schema}.record_subject rs "
        f"join {schema}.subjects s on s.id = rs.subject_id"
    )
    pairs = cur.fetchall()
    conn.close()
    return {"name": name, "schema": schema, "columns": columns, "records": records, "pairs": pairs}


class Matcher:
    """Same decision order as compare_subjects_to_soilvoc.py main()."""

    def __init__(self):
        self.uk_us = runpy.run_path(str(ROOT / "scripts" / "uk2us.py"))["uk_us"]
        self.concepts, self.exact = cmp.load_soilvoc()
        self.mapped = cmp.load_mapped_labels(self.concepts)
        self.decisions = cmp.load_decisions(ROOT / "curation" / "keyword_decisions.csv", self.concepts)

        def fold(d):
            o = defaultdict(set)
            for k, v in d.items():
                o[cmp.unaccent(k)] |= v
            return o

        self.exact_u, self.mapped_u = fold(self.exact), fold(self.mapped)
        sp = ROOT / "curation" / "stoplist.csv"
        qp = ROOT / "curation" / "path_qualifiers.csv"
        if qp.exists():
            cmp.QUALIFIERS.update(cmp.norm(r["qualifier"]) for r in cmp.read_csv(qp))
        self.stop = {cmp.norm(r["word"]) for r in cmp.read_csv(sp)} if sp.exists() else set()
        self.cache = {}

    def keyword(self, t, raw):
        if t in self.cache:
            return self.cache[t]
        dec = self.decisions.get(t)
        if dec and dec["decision"] in ("synonym", "broader"):
            r = ("manual", {dec["target_concept_uri"]})
        elif (dec and dec["decision"] == "noise") or cmp.is_noise(t):
            r = ("noise", set())
        else:
            tier, ids, _rule, _clean = cmp.match(
                t, self.exact, self.mapped, self.uk_us, raw, self.exact_u, self.mapped_u, self.stop)
            r = (tier, ids)
        if r[0] not in cmp.MATCH_TIERS:
            r = ("none", set())
        self.cache[t] = r
        return r

    def label(self, label):
        """SoilVoc concept ids for one stored subject label (may hold several keywords)."""
        whole = cmp.norm(label or "")
        if whole and cmp.is_noise(whole):
            parts = [(whole, whole)]
        else:
            parts = [(cmp.norm(p), p.strip()) for p in cmp.split_raw(label or "") if cmp.norm(p)]
        ids = set()
        for t, raw in parts:
            tier, got = self.keyword(t, raw)
            if tier != "none":
                ids |= got
        return ids


def profile(db, matcher):
    """identifier -> {labels, concept ids}. Records without identifier are skipped and counted."""
    labels_of = defaultdict(set)
    for rid, label in db["pairs"]:
        if label:
            labels_of[rid].add(label)
    out, missing = {}, 0
    for rid, ident, title, harvest, created in db["records"]:
        if not ident:
            missing += 1
            continue
        labs = labels_of.get(rid, set())
        ids = set()
        for lab in labs:
            ids |= matcher.label(lab)
        out[ident] = {"title": title or "", "created": created, "harvest": harvest, "labels": labs, "ids": ids}
    return out, missing


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT / ".env"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "stage_vs_dev"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    env = cmp.load_env(args.env)
    stage, dev = fetch(env, "1"), fetch(env, "2")
    same_schema = stage["columns"] == dev["columns"]
    print(f"{stage['name']}.{stage['schema']} vs {dev['name']}.{dev['schema']}  schema identical: {same_schema}")
    if not same_schema:
        a, b = set(stage["columns"]), set(dev["columns"])
        for c in sorted(a - b):
            print("  only in stage:", c)
        for c in sorted(b - a):
            print("  only in dev:  ", c)
        raise SystemExit("schemas differ; not comparing")

    m = Matcher()
    ps, miss_s = profile(stage, m)
    pd_, miss_d = profile(dev, m)
    both = sorted(set(ps) & set(pd_))
    only_dev = sorted(set(pd_) - set(ps))
    only_stage = sorted(set(ps) - set(pd_))
    dup_s = len(stage["records"]) - miss_s - len(ps)
    dup_d = len(dev["records"]) - miss_d - len(pd_)

    def stats(keys, p):
        n = len(keys)
        subj = sum(1 for k in keys if p[k]["labels"])
        soil = sum(1 for k in keys if p[k]["ids"])
        return n, subj, soil

    def concept_text(ids):
        ids = sorted(ids)
        return " | ".join(m.concepts[i]["label"] for i in ids), " | ".join(ids)

    def row(k, p):
        r = p[k]
        lab, uri = concept_text(r["ids"])
        return [k, r["title"][:150], r["created"].date() if r["created"] else "", len(r["labels"]),
                len(r["ids"]), lab, uri, " | ".join(sorted(r["labels"]))[:300]]

    head = ["identifier", "title", "created_at", "n_subjects", "n_soilvoc_concepts", "soilvoc_labels", "soilvoc_uris", "subjects"]
    write_csv(out / "new_in_dev.csv", head, [row(k, pd_) for k in only_dev])
    write_csv(out / "new_in_dev_with_soilvoc.csv", head, [row(k, pd_) for k in only_dev if pd_[k]["ids"]])
    write_csv(out / "new_in_dev_without_subjects.csv", head[:5], [row(k, pd_)[:5] for k in only_dev if not pd_[k]["labels"]])
    write_csv(out / "only_in_stage.csv", head, [row(k, ps) for k in only_stage])

    changed = []
    for k in both:
        a, b = ps[k], pd_[k]
        if a["labels"] != b["labels"]:
            changed.append([
                k, a["title"][:150], len(a["labels"]), len(b["labels"]),
                len(a["ids"]), len(b["ids"]),
                " | ".join(sorted(b["labels"] - a["labels"]))[:300],
                " | ".join(sorted(a["labels"] - b["labels"]))[:300],
                concept_text(b["ids"] - a["ids"])[0],
            ])
    write_csv(out / "common_subjects_changed.csv",
              ["identifier", "title", "subjects_stage", "subjects_dev", "soilvoc_stage", "soilvoc_dev",
               "subjects_added_in_dev", "subjects_missing_in_dev", "soilvoc_labels_added_in_dev"], changed)

    # SoilVoc concepts used by the fresh records
    cc = Counter()
    for k in only_dev:
        cc.update(pd_[k]["ids"])
    write_csv(out / "new_in_dev_soilvoc_concepts.csv", ["soilvoc_label", "soilvoc_uri", "records"],
              [[m.concepts[i]["label"], i, n] for i, n in cc.most_common()])

    gained_subj = sum(1 for k in both if not ps[k]["labels"] and pd_[k]["labels"])
    gained_soil = sum(1 for k in both if not ps[k]["ids"] and pd_[k]["ids"])
    sb = sum(1 for k in both if ps[k]["labels"]); db_ = sum(1 for k in both if pd_[k]["labels"])
    sl = sum(len(ps[k]["labels"]) for k in both); dl = sum(len(pd_[k]["labels"]) for k in both)
    sc_ = sum(1 for k in both if ps[k]["ids"]); dc = sum(1 for k in both if pd_[k]["ids"])
    scl = sum(len(ps[k]["ids"]) for k in both); dcl = sum(len(pd_[k]["ids"]) for k in both)
    lost_subj = sum(1 for k in both if ps[k]["labels"] and not pd_[k]["labels"])

    lines = [f"# Stage vs dev: subjects and SoilVoc", "",
             f"Stage = `{stage['name']}` (schema `{stage['schema']}`), dev = `{dev['name']}` (schema `{dev['schema']}`). Read-only.", "",
             f"Schema check: tables {', '.join(TABLES)} have identical columns in both databases.", "",
             "## Records by identifier", "",
             "| Group | Records | With subjects | With SoilVoc concept |", "|---|---|---|---|"]
    for name, keys, p in (("Stage, all", list(ps), ps), ("Dev, all", list(pd_), pd_),
                          ("In both", both, ps), ("Only in dev (fresh)", only_dev, pd_),
                          ("Only in stage", only_stage, ps)):
        n, s, so = stats(keys, p)
        lines.append(f"| {name} | {n:,} | {s:,} ({pct(s, n)}) | {so:,} ({pct(so, n)}) |")
    lines += ["", f"Records without an identifier (skipped): stage {miss_s}, dev {miss_d}. "
              f"Duplicate identifiers (collapsed): stage {dup_s}, dev {dup_d}.", "",
              "## Records present in both", "",
              f"The {len(both):,} records in both are {pct(len(both), len(ps))} of stage and {pct(len(both), len(pd_))} of dev.", "",
              "| Same records | In stage | In dev | Change |", "|---|---|---|---|",
              f"| Records with subjects | {sb:,} ({pct(sb, len(both))}) | {db_:,} ({pct(db_, len(both))}) | {db_ - sb:+,} |",
              f"| Subject links | {sl:,} | {dl:,} | {dl - sl:+,} |",
              f"| Records with a SoilVoc concept | {sc_:,} ({pct(sc_, len(both))}) | {dc:,} ({pct(dc, len(both))}) | {dc - sc_:+,} |",
              f"| SoilVoc concept links | {scl:,} | {dcl:,} | {dcl - scl:+,} |", "",
              f"- Subjects differ for {len(changed):,} of {len(both):,} records (`common_subjects_changed.csv`).",
              f"- Gained their first subjects in dev: {gained_subj:,}. Lost all subjects in dev: {lost_subj:,}.",
              f"- Gained their first SoilVoc concept in dev: {gained_soil:,}.", "",
              "## Files", "",
              "- `new_in_dev.csv`: fresh records with subjects and matched SoilVoc concepts",
              "- `new_in_dev_with_soilvoc.csv`: fresh records that have at least one SoilVoc concept",
              "- `new_in_dev_without_subjects.csv`: fresh records with no subjects (candidates for text extraction)",
              "- `new_in_dev_soilvoc_concepts.csv`: SoilVoc concepts used by the fresh records",
              "- `only_in_stage.csv`: records in stage but not in dev",
              "- `common_subjects_changed.csv`: records in both whose subjects differ",
              "- `full_comparison.md`, `field_changes.csv`: all other fields (title, abstract, ...) for records in both", "",
              "SoilVoc matching: exact, mapped, variant, normalised and manual decisions, the same rules as "
              "`reports/subjects_vs_soilvoc`. Suggestion-only translated matches are not counted.", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
