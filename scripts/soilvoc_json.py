# Usage: python scripts/soilvoc_json.py reports/soilvoc_keywords_by_level.csv reports/soilvoc_hierarchy.json
# Nested JSON tree of the SoilVoc hierarchy (primary/shortest-path tree, same as the CSV).
# Uses "name"/"children" keys so it loads directly into D3 hierarchy/tree layouts.
import csv, json, sys
rows = list(csv.DictReader(open(sys.argv[1])))
tree = [r for r in rows if r["level"]]
path = lambda r: tuple(r[f"L{i}"] for i in range(1, int(r["level"]) + 1))
nodes = {}
for r in sorted(tree, key=lambda r: int(r["level"])):
    p = path(r)
    others = [x for x in r["all_parents"].split("; ") if x and x != r["parent"]]
    n = {"name": r["prefLabel"], "uri": r["uri"], "level": int(r["level"])}
    if others: n["other_parents"] = others
    n["children"] = []
    nodes[p] = n
    if len(p) > 1: nodes[p[:-1]]["children"].append(n)
def finish(n):
    n["children"].sort(key=lambda c: c["name"].lower())
    n["descendants"] = sum(finish(c) + 1 for c in n["children"])
    if not n["children"]: del n["children"]
    return n["descendants"]
tops = sorted((n for p, n in nodes.items() if len(p) == 1), key=lambda n: n["name"].lower())
for t in tops: finish(t)
out = {
    "name": "SoilVoc", "source": "SoilVoc.ttl",
    "concepts_in_hierarchy": len(tree), "max_level": max(int(r["level"]) for r in tree),
    "children": tops,
    "detached_procedure_codes": sorted(({"name": r["prefLabel"], "uri": r["uri"],
        **({"parent": r["parent"]} if r["parent"] else {})} for r in rows if not r["level"]),
        key=lambda d: d["name"].lower()),
}
json.dump(out, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
count = lambda n: 1 + sum(count(c) for c in n.get("children", []))
print("tree nodes", sum(count(t) for t in tops), "detached", len(out["detached_procedure_codes"]))
