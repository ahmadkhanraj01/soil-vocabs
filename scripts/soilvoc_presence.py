# Usage: python scripts/soilvoc_presence.py
# Combines DB subject matches (reports/soilvoc_levels_vs_db/soilvoc_levels_with_db.csv) and
# title/abstract hits (reports/soilvoc_in_title_abstract/concept_hits.csv) into one status per concept:
#   absent  - not in any subject and not in any title/abstract
#   weak    - found, but in WEAK_MAX records or fewer (largest of the subject and text counts),
#             or only through an ambiguous everyday word (e.g. "lead")
#   strong  - everything else
import csv
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WEAK_MAX = 5
db = {r["uri"]: r for r in csv.DictReader(open(ROOT / "reports/soilvoc_levels_vs_db/soilvoc_levels_with_db.csv"))}
tx = {r["uri"]: r for r in csv.DictReader(open(ROOT / "reports/soilvoc_in_title_abstract/concept_hits.csv"))}
rows = []
for u, r in db.items():
    t = tx.get(u, {})
    sub = int(r["db_records"] or 0); text = int(t.get("records_any") or 0); amb = t.get("ambiguous_word") == "yes"
    where = ("subjects + text" if sub and text else "subjects only" if sub else "text only" if text else "nowhere")
    n = max(sub, text)
    status = "absent" if n == 0 else "weak" if n <= WEAK_MAX or (amb and not sub) else "strong"
    rows.append(dict(status=status, found_in=where, level=r["level"] or "procedure code", prefLabel=r["prefLabel"],
                     top_concept=r["top_concept"], subject_records=sub, text_records=text,
                     ambiguous_word="yes" if amb else "", uri=u))
order = {"absent": 0, "weak": 1, "strong": 2}
rows.sort(key=lambda x: (order[x["status"]], x["level"] == "procedure code", x["level"], x["prefLabel"].lower()))
out = ROOT / "reports/soilvoc_levels_vs_db/concept_presence.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
voc = [x for x in rows if x["level"] != "procedure code"]; proc = [x for x in rows if x["level"] == "procedure code"]
print("vocabulary terms", len(voc), Counter(x["status"] for x in voc))
print("procedure codes", len(proc), Counter(x["status"] for x in proc))
print("found_in (vocab):", Counter(x["found_in"] for x in voc))
lv = defaultdict(Counter)
for x in voc: lv[x["level"]][x["status"]] += 1
for k in sorted(lv): print("level", k, dict(lv[k]))
tc = defaultdict(Counter)
for x in voc: tc[x["top_concept"]][x["status"]] += 1
for k, c in sorted(tc.items(), key=lambda kv: -sum(kv[1].values())): print(k, dict(c), sum(c.values()))
print("weak examples:", [x["prefLabel"] for x in voc if x["status"] == "weak"][:15])
print("absent examples:", [x["prefLabel"] for x in voc if x["status"] == "absent"][:20])
