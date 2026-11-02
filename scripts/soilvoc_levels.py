# Usage: python scripts/soilvoc_levels.py SoilVoc.ttl reports/soilvoc_keywords_by_level.csv
import csv, sys
from collections import defaultdict, deque, Counter
from rdflib import Graph, Namespace, RDF
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
g = Graph().parse(sys.argv[1])
concepts = set(g.subjects(RDF.type, SKOS.Concept))
label = {c: str(g.value(c, SKOS.prefLabel) or str(c).split('#')[-1]) for c in concepts}
lab = lambda c: label.get(c, str(c))
parents = defaultdict(set)
for c, p in g.subject_objects(SKOS.broader): parents[c].add(p)
for p, c in g.subject_objects(SKOS.narrower): parents[c].add(p)
children = defaultdict(set)
for c, ps in parents.items():
    for p in ps: children[p].add(c)
tops = {c for c in concepts if (c, SKOS.topConceptOf, None) in g} | (set(g.objects(None, SKOS.hasTopConcept)) & concepts)

def bfs(roots, path):
    q = deque()
    for t in sorted(roots, key=lambda x: lab(x).lower()):
        if t not in path: path[t] = [t]; q.append(t)
    while q:
        n = q.popleft()
        for ch in sorted(children[n], key=lambda x: lab(x).lower()):
            if ch not in path: path[ch] = path[n] + [ch]; q.append(ch)

main = {}; bfs(tops, main)
detached = {}; bfs({c for c in concepts - set(main) if not parents[c]}, detached)
assert set(main) | set(detached) >= concepts
maxd = max(len(p) for p in main.values())
rows = []
for c in concepts:
    inh = c in main
    p = main[c] if inh else detached[c]
    rows.append(dict(
        level=len(p) if inh else "", prefLabel=label[c],
        top_concept=lab(p[0]) if inh else "", parent=lab(p[-2]) if len(p) > 1 else "",
        all_parents="; ".join(sorted(lab(x) for x in parents[c])),
        n_children=len(children[c]),
        **{f"L{i+1}": (lab(p[i]) if inh and i < len(p) else "") for i in range(maxd)},
        in_hierarchy="yes" if inh else "no (detached procedure code)",
        uri=str(c)))
rows.sort(key=lambda r: (r["in_hierarchy"] != "yes", [r[f"L{i+1}"].lower() for i in range(maxd)], r["parent"].lower(), r["prefLabel"].lower()))
with open(sys.argv[2], "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("concepts", len(concepts), "in hierarchy", len(main), "detached", len(detached), "maxdepth", maxd)
print(sorted(Counter(r["level"] for r in rows if r["level"] != "").items()))
print("multi-parent", sum(1 for c in concepts if len(parents[c]) > 1))
