# Usage: python scripts/soilvoc_levels_vs_db.py <matched.csv> reports/soilvoc_keywords_by_level.csv <out_dir> "<db label>"
# Joins the DB keyword matches (matched.csv from compare_subjects_to_soilvoc.py) with the SoilVoc levels CSV.
# "records" = sum of record counts over the keywords matched to a concept; a record tagged with two
# keywords that map to the same concept is counted twice, so treat it as an upper bound.
import csv, sys
from collections import defaultdict, Counter
from pathlib import Path
matched, levels_csv, out, db = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
out.mkdir(parents=True, exist_ok=True)
COUNTED = {"exact", "mapped", "variant", "normalised", "normalised_path", "normalised_prefix", "manual"}
kw = defaultdict(list)
for r in csv.DictReader(open(matched)):
    if r["match_tier"] in COUNTED and r["soilvoc_uri"]:
        # ambiguous matches list several URIs ("a | b"); credit each concept
        for u in r["soilvoc_uri"].split(" | "):
            kw[u.strip()].append((r["keyword"], int(r["records"]), r["match_tier"]))
rows = list(csv.DictReader(open(levels_csv)))
uris = {r["uri"] for r in rows}
missing = set(kw) - uris
maxd = max(int(r["level"]) for r in rows if r["level"])
path = lambda r: tuple(r[f"L{i}"] for i in range(1, int(r["level"]) + 1))

# per-concept columns + subtree roll-up (concept and all its descendants in the primary tree)
sub_hit, sub_n, sub_rec = Counter(), Counter(), Counter()
for r in rows:
    k = kw.get(r["uri"], [])
    r["db_keyword_count"] = len(k)
    r["db_records"] = sum(n for _, n, _ in k)
    r["db_keywords"] = "; ".join(f"{w} ({n})" for w, n, _ in sorted(k, key=lambda x: -x[1]))
    r["db_match_tiers"] = "; ".join(sorted({t for _, _, t in k}))
    if r["level"]:
        p = path(r)
        for i in range(1, len(p) + 1):
            sub_n[p[:i]] += 1; sub_rec[p[:i]] += r["db_records"]; sub_hit[p[:i]] += bool(k)
for r in rows:
    if r["level"]:
        p = path(r)
        r["subtree_concepts"], r["subtree_hit"], r["subtree_db_records"] = sub_n[p], sub_hit[p], sub_rec[p]
    else:
        r["subtree_concepts"] = r["subtree_hit"] = r["subtree_db_records"] = ""
cols = ["level", "prefLabel", "in_db", "db_keyword_count", "db_records", "db_keywords", "db_match_tiers",
        "subtree_concepts", "subtree_hit", "subtree_db_records", "top_concept", "parent", "all_parents",
        "n_children"] + [f"L{i}" for i in range(1, maxd + 1)] + ["in_hierarchy", "uri"]
for r in rows: r["in_db"] = "yes" if r["db_keyword_count"] else "no"
with open(out / "soilvoc_levels_with_db.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

pct = lambda a, b: f"{100*a/b:.1f}%" if b else "-"
def table(groups, keyf, header):
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for r in groups:
        a = agg[keyf(r)]; a[0] += 1; a[1] += r["in_db"] == "yes"; a[2] += r["db_keyword_count"]; a[3] += r["db_records"]
    return agg
by_level = table(rows, lambda r: r["level"] or "detached", "level")
order = [str(i) for i in range(1, maxd + 1)] + ["detached"]
with open(out / "coverage_by_level.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["level", "concepts", "concepts_in_db", "pct_in_db", "db_keywords", "db_records"])
    for k in order:
        a = by_level[k]; w.writerow([k, a[0], a[1], pct(a[1], a[0]), a[2], a[3]])
tree = [r for r in rows if r["level"]]
with open(out / "coverage_by_branch.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["top_concept", "level2", "concepts", "concepts_in_db", "pct_in_db", "db_keywords", "db_records"])
    for key, a in sorted(table(tree, lambda r: (r["L1"], r["L2"]), "").items(), key=lambda kv: (kv[0][0], -kv[1][3])):
        w.writerow([key[0], key[1] or "(the top concept itself)", a[0], a[1], pct(a[1], a[0]), a[2], a[3]])

tot = len(rows); hit = sum(r["in_db"] == "yes" for r in rows)
L = [f"# SoilVoc levels vs database keywords", "",
     f"Database: {db} (read-only). Matches from `compare_subjects_to_soilvoc.py` "
     "(tiers exact, mapped, variant, normalised*, manual; translated suggestions not counted).", "",
     f"SoilVoc concepts found in the database: **{hit} of {tot} ({pct(hit, tot)})**.", "",
     "`db_records` sums record counts over all keywords matched to a concept, so a record with two "
     "matching keywords counts twice: read it as an upper bound. A keyword matched to several concepts (e.g. FAO and WRB `Andosols`) counts for each of them.", "",
     "## Coverage by level", "", "| Level | Concepts | In DB | % | DB keywords | DB records |", "|---|---|---|---|---|---|"]
for k in order:
    a = by_level[k]; L.append(f"| {k} | {a[0]} | {a[1]} | {pct(a[1], a[0])} | {a[2]} | {a[3]} |")
L += ["", "## Coverage by top concept", "", "| Top concept | Concepts | In DB | % | DB records |", "|---|---|---|---|---|"]
tops = sorted((r for r in tree if r["level"] == "1"), key=lambda r: -r["subtree_concepts"])
for t in tops:
    L.append(f"| {t['prefLabel']} | {t['subtree_concepts']} | {t['subtree_hit']} | {pct(t['subtree_hit'], t['subtree_concepts'])} | {t['subtree_db_records']} |")
L += ["", "## Most used concepts", "", "| Level | Concept | Top concept | DB records | Keywords |", "|---|---|---|---|---|"]
for r in sorted(rows, key=lambda r: -r["db_records"])[:25]:
    kws = r["db_keywords"] if len(r["db_keywords"]) < 90 else r["db_keywords"][:87] + "..."
    L.append(f"| {r['level'] or '-'} | {r['prefLabel']} | {r['top_concept'] or '-'} | {r['db_records']} | {kws} |")
L += ["", "## Branches with no database hits (level 2, 3+ concepts)", ""]
for key, a in sorted(table(tree, lambda r: (r["L1"], r["L2"]), "").items()):
    if key[1] and a[1] == 0 and a[0] >= 3: L.append(f"- {key[0]} › {key[1]} ({a[0]} concepts)")
L += ["", "## Files", "", "- `soilvoc_levels_with_db.csv`: the levels CSV plus DB keywords, record counts and subtree roll-ups",
      "- `coverage_by_level.csv`, `coverage_by_branch.csv`: the tables above as CSV"]
if missing: L += ["", f"Note: {len(missing)} matched URIs are not in the levels CSV: " + ", ".join(sorted(missing))]
(out / "report.md").write_text("\n".join(L) + "\n")
print("hit", hit, "of", tot, "missing uris", len(missing))
