"""Build the dry-run link set for Option 1 (Step 3). Read-only, no DB writes.

Usage: python scripts/build_soilvoc_links.py
       [--subjects reports/subjects_cleaned/subjects_cleaned.csv]
       [--review curation/inside_keyword_review.csv]
       [--out reports/soilvoc_levels_vs_db/dry_run_links.csv]
       [--db 1]              # read-only, stage, for record counts

Reads the cleaned-subjects CSV and the inside-keyword review, and writes one row per
(subject, SoilVoc concept) link that load_soilvoc_links.py would insert:

  subject_id, original_label, part, link_type, soilvoc_uri, soilvoc_label, level,
  reviewed, records, note

Link rules (reports/soilvoc_levels_vs_db/IMPLEMENTATION.md, Option 1):
  status=soilvoc          -> link_type from relation (accents -> variant), reviewed=true
  status=soilvoc-partial  -> join curation/inside_keyword_review.csv on the label:
                               same / narrower -> link_type='inside', reviewed=true
                               unclear          -> link_type='inside', reviewed=false
                               wrong            -> NOT inserted
                             rows with no review verdict -> skipped (reported)
  status=soilvoc-ambiguous-> every candidate inserted with reviewed=false (a person decides)
  proposed-new-term       -> skipped (not in SoilVoc yet)
  noise / category-label  -> no link; goes to subjects.vocabulary_name='noise'
  unclassified            -> no link, stays empty

Also prints a validation block against the PLAN.md targets
(483 concepts, 5,916 direct records, 6,050 records incl. inside links).
"""
import argparse
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "reports" / "soilvoc_levels_vs_db" / "PLAN.md"

# PLAN.md targets (Option 1)
TARGET_CONCEPTS = 483        # 476 direct + 7 kept from the inside review
TARGET_RECORDS_DIRECT = 5916  # records with a direct (whole-subject) SoilVoc link
TARGET_RECORDS_ALL = 6050     # incl. reviewed inside links

REL_TO_LINK = {
    "exact": "exact", "synonym": "synonym", "translation": "translation",
    "mapped": "mapped", "variant": "variant", "accents": "variant",
    "broader": "broader",
}
# inside-review verdicts -> (insert?, reviewed)
VERDICTS = {
    "same": (True, True),        # becomes a normal (reviewed) link
    "narrower": (True, True),    # safe as a broader link, kept apart as 'inside'
    "unclear": (True, False),    # inserted but flagged for a person
    "wrong": (False, False),     # not inserted
}


def norm(s):
    s = unicodedata.normalize("NFKC", (s or "")).lower()
    return re.sub(r"[\s_\-]+", " ", s).strip()


def load_review(path):
    """(norm(keyword), soilvoc_uri) -> list of verdicts."""
    out = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out[(norm(row["keyword"]), row["soilvoc_uri"])].append(row["verdict"])
    return out


def load_decisions(path):
    """{(subject_id, soilvoc_uri): (verdict, sheet_row)} from a filled review sheet.

    sheet_row keeps every column so 'keep' can re-add a link the builder skipped
    (e.g. a pair missing from curation/inside_keyword_review.csv).
    """
    if path is None:
        path = ROOT / "reports" / "soilvoc_levels_vs_db" / "review_sheet.csv"
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            verdict = (row.get("verdict") or "").strip().lower()
            if verdict in ("keep", "drop"):
                out[(row["subject_id"], row["soilvoc_uri"])] = (verdict, row)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subjects", default=str(ROOT / "reports/subjects_cleaned/subjects_cleaned.csv"))
    ap.add_argument("--review", default=str(ROOT / "curation/inside_keyword_review.csv"))
    ap.add_argument("--out", default=str(ROOT / "reports/soilvoc_levels_vs_db/dry_run_links.csv"))
    ap.add_argument("--db", choices=("1",), default="1",
                    help="for record counts, read-only (default 1=stage: "
                         "the CSV's subject ids come from stage)")
    ap.add_argument("--decisions", default=None,
                    help="review sheet (review_sheet.csv) with a filled 'verdict' "
                         "column: 'keep' marks the row reviewed, 'drop' removes it "
                         "(default: reports/soilvoc_levels_vs_db/review_sheet.csv "
                         "if it has any verdicts)")
    args = ap.parse_args()

    with open(args.subjects, newline="") as f:
        rows = list(csv.DictReader(f))
    review = load_review(args.review)

    links = {}            # (subject_id, uri) -> link dict
    skipped = Counter()   # reason -> rows
    no_verdict = []       # (label, uri) pairs missing from the review
    ambiguous = []        # rows a person must decide
    noise_rows = defaultdict(list)   # subject -> its rows (for the all-noise rule)
    soilvoc_subjects = set()

    def add_link(r, uri, label, link_type, reviewed, note, part=None, level=None):
        key = (r["subject_id"], uri)
        if key in links:
            # a direct link beats an inside link for the same concept
            if links[key]["link_type"] == "inside" and link_type != "inside":
                links[key].update(link_type=link_type, reviewed=reviewed, note=note)
            return
        if level is None:
            level = r["soilvoc_level"]
        links[key] = {
            "subject_id": r["subject_id"], "original_label": r["original_label"],
            "part": part if part is not None else r["part"], "link_type": link_type,
            "soilvoc_uri": uri, "soilvoc_label": label, "level": level,
            "reviewed": reviewed, "records": r["records"], "note": note,
        }

    def split_field(r, field):
        """Multi-concept rows join values with ';': 'uri1; uri2', '1; 2', ..."""
        return [x.strip() for x in (r[field] or "").split(";")]

    def review_verdict(r, uri):
        """verdict for one single-URI pair, or None if not in the review."""
        for field in ("part", "cleaned", "original_label"):
            key = (norm(r[field]), uri)
            if key in review:
                return review[key][0]
        return None

    for r in rows:
        st = r["status"]
        if st in ("noise", "category-label"):
            noise_rows[r["subject_id"]].append(r)
        if st == "soilvoc" and r["soilvoc_uri"]:
            lt = REL_TO_LINK.get(r["relation"])
            if not lt:
                skipped[f"unknown relation {r['relation']!r}"] += 1
                continue
            add_link(r, r["soilvoc_uri"], r["soilvoc_label"], lt, True,
                     f"relation={r['relation']}")
            soilvoc_subjects.add(r["subject_id"])
        elif st == "soilvoc-partial" and r["soilvoc_uri"]:
            # rows may carry several concepts ('soil erosion control' -> 2 URIs):
            # split them and look up each pair in the review on its own
            uris = split_field(r, "soilvoc_uri")
            labels = split_field(r, "soilvoc_label")
            levels = split_field(r, "soilvoc_level")
            for i, uri in enumerate(uris):
                label = labels[i] if i < len(labels) else r["soilvoc_label"]
                level = levels[i] if i < len(levels) else None
                verdict = review_verdict(r, uri)
                if verdict is None:
                    no_verdict.append((r["part"], uri))
                    skipped["inside, not in review"] += 1
                    continue
                insert, reviewed = VERDICTS[verdict]
                if insert:
                    add_link(r, uri, label, "inside", reviewed,
                             f"inside verdict={verdict}", part=r["part"], level=level)
                    soilvoc_subjects.add(r["subject_id"])
                else:
                    skipped[f"inside verdict={verdict}"] += 1
        elif st == "soilvoc-ambiguous":
            # Option 1 can store several concepts per subject: insert every
            # candidate, flagged for a person (plan: 476 direct incl. these)
            ambiguous.append(r)
            uris = split_field(r, "soilvoc_uri")
            labels = split_field(r, "soilvoc_label")
            levels = split_field(r, "soilvoc_level")
            lt = REL_TO_LINK.get(r["relation"], "exact")
            for i, uri in enumerate(uris):
                label = labels[i] if i < len(labels) else r["soilvoc_label"]
                level = levels[i] if i < len(levels) else None
                add_link(r, uri, label, lt, False, "ambiguous candidate",
                         part=r["part"], level=level)
            soilvoc_subjects.add(r["subject_id"])
        elif st == "proposed-new-term":
            skipped["proposed new term (not in SoilVoc)"] += 1
        elif st == "unclassified":
            pass
        else:
            skipped[f"status={st}"] += 1

    # a subject is noise only if EVERY part of it is noise/category (plan rule:
    # 1,534 subjects, 43,957 uses) and it has no SoilVoc link
    rows_per_subject = Counter(r["subject_id"] for r in rows)
    noise_subjects = {sid for sid, rs in noise_rows.items()
                      if len(rs) == rows_per_subject[sid]}
    noise_subjects -= soilvoc_subjects

    # ---- apply review-sheet verdicts (Step 4 loop) --------------------------
    decisions = load_decisions(args.decisions)
    if decisions:
        dropped = kept = readded = 0
        for key, (verdict, sheet_row) in decisions.items():
            if verdict == "drop":
                if links.pop(key, None) is not None:
                    dropped += 1
            elif verdict == "keep":
                if key in links:
                    links[key]["reviewed"] = True
                    links[key]["note"] += "|kept by review"
                    kept += 1
                else:
                    # not built (e.g. pair missing from the review CSV): the
                    # reviewer's keep re-adds it as a reviewed inside link
                    links[key] = {
                        "subject_id": sheet_row["subject_id"],
                        "original_label": sheet_row["original_label"],
                        "part": sheet_row["part"],
                        "link_type": sheet_row["link_type"] or "inside",
                        "soilvoc_uri": sheet_row["soilvoc_uri"],
                        "soilvoc_label": sheet_row["soilvoc_label"],
                        "level": sheet_row["level"],
                        "reviewed": True,
                        "records": sheet_row["records"],
                        "note": "kept by review (was missing from review CSV)",
                    }
                    readded += 1
        # dropped links may leave a subject with nothing linked
        still_linked = {sid for sid, _ in links}
        noise_subjects = noise_subjects - still_linked
        soilvoc_subjects &= still_linked
        print(f"review decisions applied: {kept} kept (now reviewed=true), "
              f"{readded} re-added, {dropped} dropped")

    # ---- write the dry-run file --------------------------------------------
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(next(iter(links.values())).keys()))
        w.writeheader()
        for key in sorted(links, key=lambda k: (k[0], k[1])):
            w.writerow(links[key])

    # noise list for subjects.vocabulary_name='noise' (all-parts-noise rule)
    label_of = {r["subject_id"]: r["original_label"] for r in rows}
    noise_out = Path(args.out).with_name("noise_subjects.csv")
    with noise_out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "label"])
        for sid in sorted(noise_subjects):
            w.writerow([sid, label_of.get(sid, "")])

    # ---- read-only DB counts ------------------------------------------------
    env = dotenv_values(ROOT / ".env")
    sfx = args.db
    conn = psycopg2.connect(host=env["DB_HOST" + sfx], port=env["DB_PORT" + sfx],
                            dbname=env["DB_NAME" + sfx], user=env["DB_USER" + sfx],
                            password=env["DB_PASSWORD" + sfx], connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute("SELECT subject_id, record_id FROM validate.record_subject")
        subj_records = defaultdict(set)
        for sid, rid in cur.fetchall():
            subj_records[sid].add(rid)
        cur.execute("SELECT COUNT(*) FROM validate.subjects")
        db_subjects = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM validate.record_subject")
        db_uses = cur.fetchone()[0]
    conn.close()

    def records_for(pred):
        recs = set()
        for (sid, _uri), link in links.items():
            if pred(link):
                recs |= subj_records.get(sid, set())
        return recs

    direct = records_for(lambda l: l["link_type"] != "inside")
    # PLAN.md counts reviewed inside links only (unclear ones are stored but
    # excluded from the headline numbers): 476+7=483 concepts, 6,050 records
    counted = lambda l: l["link_type"] != "inside" or l["reviewed"]
    allrec = records_for(counted)
    allrec_any = records_for(lambda l: True)
    concepts = {l["soilvoc_uri"] for l in links.values() if counted(l)}
    concepts_any = {l["soilvoc_uri"] for l in links.values()}
    concepts_direct = {l["soilvoc_uri"] for l in links.values()
                       if l["link_type"] != "inside"}
    strict_no_broader = records_for(
        lambda l: l["link_type"] not in ("inside", "broader"))

    print(f"dry run written: {out.relative_to(ROOT)}")
    print(f"  noise list         : {noise_out.relative_to(ROOT)} ({len(noise_subjects)} subjects)")
    print(f"  link rows          : {len(links)}")
    print(f"  subjects linked    : {len({sid for sid, _ in links})}")
    print(f"  concepts  (target {TARGET_CONCEPTS}): {len(concepts)} "
          f"(direct {len(concepts_direct)} incl. ambiguous, "
          f"+reviewed inside {len(concepts) - len(concepts_direct)}; "
          f"incl. unclear: {len(concepts_any)})")
    print(f"  records direct (target {TARGET_RECORDS_DIRECT}): {len(direct)}")
    print(f"  records all   (target {TARGET_RECORDS_ALL}): {len(allrec)} "
          f"(incl. unclear-only: {len(allrec_any)})")
    print(f"  records excl. broader+inside: {len(strict_no_broader)} "
          f"(PLAN says 5,433 without broader)")
    print(f"  link types: {dict(Counter(l['link_type'] for l in links.values()))}")
    print(f"  reviewed=false rows (not in headline counts): "
          f"{sum(1 for l in links.values() if not l['reviewed'])}")
    print(f"  noise subjects to flag: {len(noise_subjects)}")
    print(f"  skipped: {dict(skipped)}")
    if no_verdict:
        print(f"  WARNING: {len(no_verdict)} (label, uri) pairs not found in the review:")
        for part, uri in no_verdict[:10]:
            print(f"    - {part!r} -> {uri}")
    if ambiguous:
        print(f"  ambiguous rows linked with reviewed=false: {len(ambiguous)}")
    print(f"  DB: {db_subjects} subjects, {db_uses} record_subject uses")


if __name__ == "__main__":
    main()
