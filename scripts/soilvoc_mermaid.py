# Usage: python scripts/soilvoc_mermaid.py reports/soilvoc_keywords_by_level.csv reports/soilvoc_hierarchy.md
# Renders the SoilVoc hierarchy (primary/shortest-path tree) as Mermaid flowcharts.
# Oversized branches are split: big children are collapsed to a "(N concepts)" node with their own section.
import csv, re, sys
from collections import defaultdict

LIMIT = 120        # max nodes drawn in one diagram
INLINE_MAX = 25    # children with subtrees up to this size are drawn inline inside a split diagram

rows = [r for r in csv.DictReader(open(sys.argv[1])) if r["level"]]
detached = sum(1 for r in csv.DictReader(open(sys.argv[1])) if not r["level"]) 
maxd = max(int(r["level"]) for r in rows)
path = lambda r: tuple(r[f"L{i}"] for i in range(1, int(r["level"]) + 1))
children = defaultdict(list)
for r in rows:
    p = path(r)
    if len(p) > 1: children[p[:-1]].append(p)
for k in children: children[k].sort(key=lambda p: p[-1].lower())
size = {}
def sz(p):
    if p not in size: size[p] = 1 + sum(sz(c) for c in children[p])
    return size[p]
tops = sorted((path(r) for r in rows if r["level"] == "1"), key=lambda p: -sz(p))

ids = {}
nid = lambda p: ids.setdefault(p, f"n{len(ids)}")
esc = lambda s: s.replace('"', "#quot;")
anchor = lambda p: re.sub(r"[^a-z0-9 -]", "", " / ".join(p).lower()).replace(" ", "-")
title = lambda p: " › ".join(p)

sections = []  # (path, mermaid lines, collapsed children)
def diagram(root):
    lines, collapsed = [], []
    def node(p, cls=None, label=None):
        lines.append(f'    {nid(p)}["{esc(label or p[-1])}"]' + (f":::{cls}" if cls else ""))
    def full(p):
        for c in children[p]:
            node(c); lines.append(f"    {nid(p)} --> {nid(c)}"); full(c)
    node(root, "root")
    if sz(root) <= LIMIT:
        full(root)
    else:
        budget, inline = LIMIT - 1 - len(children[root]), set()
        for c in sorted(children[root], key=sz):
            extra = sz(c) - 1
            if sz(c) <= INLINE_MAX and extra <= budget: inline.add(c); budget -= extra
        for c in children[root]:
            if c in inline:
                node(c); lines.append(f"    {nid(root)} --> {nid(c)}"); full(c)
            else:
                node(c, "more", f"{c[-1]} ({sz(c)} concepts)")
                lines.append(f"    {nid(root)} --> {nid(c)}"); collapsed.append(c)
    sections.append((root, lines, collapsed))
    for c in collapsed: diagram(c)

for t in tops: diagram(t)

out = ["# SoilVoc hierarchy", "",
       f"Generated from `{sys.argv[1]}` by `scripts/soilvoc_mermaid.py`. "
       f"{len(rows)} concepts under {len(tops)} top concepts, max depth {maxd}. "
       "Concepts with several parents are drawn once, under their shortest path "
       "(see `all_parents` in the CSV). "
       f"{detached} detached GLOSIS procedure codes are not shown.", "",
       "Orange nodes are collapsed branches; their full diagram is linked in the list under each chart.", "",
       "## Overview (top concepts)", "", "```mermaid", "flowchart LR",
       '    SV(["SoilVoc"])']
for t in tops:
    out.append(f'    SV --> {nid(t)}["{esc(t[0])} ({sz(t)})"]')
out += ["```", "", "## Contents", ""]
for root, _, _ in sections:
    out.append(f"{'  ' * (len(root) - 1)}- [{root[-1]}](#{anchor(root)}) ({sz(root)})")
STYLE = ["    classDef root fill:#2b6cb0,color:#fff,stroke:#1a4971",
         "    classDef more fill:#f6ad55,stroke:#c05621"]
for root, lines, collapsed in sections:
    out += ["", f"## {' / '.join(root)}", "", f"Path: {title(root)} · {sz(root)} concepts", "",
            "```mermaid", "flowchart LR", *lines, *STYLE, "```"]
    if collapsed:
        out += ["", "Collapsed branches:"] + [f"- [{c[-1]}](#{anchor(c)}) ({sz(c)})" for c in collapsed]
open(sys.argv[2], "w").write("\n".join(out) + "\n")
print(len(sections), "diagrams; largest", max(len([l for l in s[1] if '-->' in l]) for s in sections), "edges")
