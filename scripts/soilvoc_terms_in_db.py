"""SoilVoc terms found in the DB after keyword cleaning.

Reads the outputs of clean_subjects.py (no DB access) and writes:
  reports/subjects_cleaned/soilvoc_terms_in_db.csv     one row per SoilVoc term used by records (487)
  reports/subjects_cleaned/soilvoc_keywords_in_db.csv  one row per DB keyword mapped to SoilVoc (1,063)
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "subjects_cleaned"
LEVELS = ROOT / "reports" / "soilvoc_keywords_by_level.csv"
BEFORE = ROOT / "reports" / "soilvoc_levels_vs_db" / "soilvoc_levels_with_db.csv"

STRENGTH = {"full": 0, "broader/ambiguous": 1, "inside a longer keyword": 2}

levels = {r["uri"]: r for r in csv.DictReader(open(LEVELS))}
before = {r["uri"]: r for r in csv.DictReader(open(BEFORE))}
subjects = list(csv.DictReader(open(OUT / "subjects_cleaned.csv")))
rec_links = list(csv.DictReader(open(OUT / "record_soilvoc.csv")))

# Keyword table: unique cleaned keywords with status soilvoc (the 1,063).
kw = {}
for s in subjects:
    if s["status"] != "soilvoc":
        continue
    k = kw.setdefault(s["cleaned"], {
        "keyword": s["cleaned"], "english": s["english"], "language": s["language"],
        "relation": s["relation"], "soilvoc_label": s["soilvoc_label"],
        "soilvoc_level": s["soilvoc_level"], "soilvoc_uri": s["soilvoc_uri"],
        "original_labels": set(), "records": 0})
    k["original_labels"].add(s["original_label"])
    k["records"] += int(s["records"] or 0)

# Per concept: keywords by link strength.
by_uri = defaultdict(lambda: {"full": defaultdict(int), "broader": defaultdict(int),
                              "ambiguous": defaultdict(int), "inside": defaultdict(int)})
bucket = {"soilvoc": None, "soilvoc-ambiguous": "ambiguous", "soilvoc-partial": "inside"}
for s in subjects:
    if s["status"] not in bucket:
        continue
    b = bucket[s["status"]] or ("broader" if s["relation"] == "broader" else "full")
    for u in filter(None, s["soilvoc_uri"].split(" | ")):
        by_uri[u][b][s["cleaned"]] += int(s["records"] or 0)

recs = defaultdict(lambda: defaultdict(set))
for r in rec_links:
    recs[r["soilvoc_uri"]][r["link"]].add(r["record_id"])


def fmt(d):
    return "; ".join(f"{k} ({v})" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])))


rows = []
for uri, links in recs.items():
    lv = levels.get(uri, {})
    best = min(links, key=STRENGTH.get)
    full = links.get("full", set())
    strong = full | links.get("broader/ambiguous", set())
    allr = strong | links.get("inside a longer keyword", set())
    k = by_uri[uri]
    b = before.get(uri, {})
    rows.append({
        "level": lv.get("level", ""), "soilvoc_term": lv.get("prefLabel", ""),
        "top_concept": lv.get("top_concept", ""), "parent": lv.get("parent", ""),
        "best_link": best,
        "n_keywords": len(k["full"]), "n_keywords_broader": len(k["broader"]),
        "n_keywords_ambiguous": len(k["ambiguous"]), "n_keywords_inside": len(k["inside"]),
        "records_full": len(full), "records_incl_broader": len(strong),
        "records_incl_inside": len(allr),
        "in_db_before_cleaning": b.get("in_db", ""),
        "keywords": fmt(k["full"]), "keywords_broader": fmt(k["broader"]),
        "keywords_ambiguous": fmt(k["ambiguous"]), "keywords_inside": fmt(k["inside"]),
        "uri": uri,
    })
rows.sort(key=lambda r: (STRENGTH[r["best_link"]], -r["records_incl_inside"], r["soilvoc_term"]))

with open(OUT / "soilvoc_terms_in_db.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

kws = sorted(kw.values(), key=lambda k: (-k["records"], k["keyword"]))
for k in kws:
    k["original_labels"] = " | ".join(sorted(k["original_labels"]))
with open(OUT / "soilvoc_keywords_in_db.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["keyword", "english", "language", "relation", "soilvoc_label",
                                      "soilvoc_level", "soilvoc_uri", "records", "original_labels"])
    w.writeheader()
    w.writerows(kws)

cnt = defaultdict(int)
for r in rows:
    cnt[r["best_link"]] += 1
strong = cnt["full"] + cnt["broader/ambiguous"]
print(f"SoilVoc terms in DB: {len(rows)} (direct keyword {strong}, of which only via broader/ambiguous "
      f"{cnt['broader/ambiguous']}; only inside a longer keyword {cnt['inside a longer keyword']})")
print(f"Unique DB keywords mapped to SoilVoc: {len(kws)}")
print(f"Terms in DB before cleaning: {sum(1 for r in before.values() if r['in_db'] == 'yes')}")
