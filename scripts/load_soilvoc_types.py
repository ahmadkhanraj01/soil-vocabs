"""Load SoilVoc concepts into validate.soilvoc_types (Option 1, Step 2). Idempotent.

Usage: python scripts/load_soilvoc_types.py [--db 1] [--ttl SoilVoc.ttl]

Sources all skos:Concept from the TTL:
  name        = skos:prefLabel
  alt_labels  = all skos:altLabel literals (sorted, unique)
  level       = depth from a top concept (1..8), same BFS as scripts/soilvoc_levels.py;
                NULL for concepts outside the hierarchy (detached SOSA procedure codes)
  parent_code = tree parent from the same BFS as scripts/soilvoc_levels.py, so it
                matches reports/soilvoc_hierarchy.json (first parent reached, children
                in label order). Detached procedure codes keep their detached group
                code as parent (level stays NULL). 131 concepts have several parents;
                all of them go to reports/soilvoc_levels_vs_db/multi_parent_concepts.csv

Load order: upsert every row with parent_code NULL first, then set parent_code in a
second pass, so foreign keys are always satisfied regardless of graph order.
No TRUNCATE: re-running after subject_soilvoc has links must not delete them.
"""
import argparse
import csv
import sys
from collections import defaultdict, deque
from pathlib import Path

import psycopg2
from dotenv import dotenv_values
from psycopg2.extras import execute_values
from rdflib import Graph, Namespace, RDF

ROOT = Path(__file__).resolve().parent.parent
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
MULTI_OUT = ROOT / "reports" / "soilvoc_levels_vs_db" / "multi_parent_concepts.csv"

# expected level histogram (from scripts/soilvoc_levels.py on SoilVoc.ttl, 2026-11-03)
EXPECTED_LEVELS = {1: 17, 2: 144, 3: 300, 4: 305, 5: 242, 6: 133, 7: 5, 8: 69}
EXPECTED_CONCEPTS = 1464


def compute_tree(concepts, parents, g):
    """Same BFS as scripts/soilvoc_levels.py (and so the same tree as
    reports/soilvoc_hierarchy.json): roots and children visited in label order,
    each concept's tree parent is the one that reaches it first.

    Returns (levels, tree_parent): levels only for concepts under a top concept;
    tree_parent also for detached procedure codes under a detached group code.
    """
    label = {c: str(g.value(c, SKOS.prefLabel) or str(c).split("#")[-1]).lower() for c in concepts}
    children = defaultdict(set)
    for c, ps in parents.items():
        for p in ps:
            children[p].add(c)
    tops = {c for c in concepts if (c, SKOS.topConceptOf, None) in g} | \
           (set(g.objects(None, SKOS.hasTopConcept)) & concepts)

    def bfs(roots, depth, parent):
        queue = deque()
        for t in sorted(roots, key=lambda x: label[x]):
            if t not in depth:
                depth[t] = 1
                queue.append(t)
        while queue:
            node = queue.popleft()
            for ch in sorted(children[node], key=lambda x: label[x]):
                if ch not in depth:
                    depth[ch] = depth[node] + 1
                    parent[ch] = node
                    queue.append(ch)

    levels, tree_parent = {}, {}
    bfs(tops, levels, tree_parent)
    detached_depth = {}
    bfs({c for c in concepts - set(levels) if not parents.get(c)}, detached_depth, tree_parent)
    return levels, tree_parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", choices=("1",), default="1", help="1=stage (msp-kh-stage, schema validate). Dev is never written.")
    ap.add_argument("--ttl", default=str(ROOT / "SoilVoc.ttl"))
    args = ap.parse_args()

    # ---- read the TTL -------------------------------------------------------
    g = Graph().parse(args.ttl)
    concepts = set(g.subjects(RDF.type, SKOS.Concept))

    parents = defaultdict(set)
    for c, p in g.subject_objects(SKOS.broader):
        parents[c].add(p)
    for p, c in g.subject_objects(SKOS.narrower):   # same as soilvoc_levels.py
        parents[c].add(p)
    # only keep parents that are concepts themselves (FK target must exist)
    parents = {c: {p for p in ps if p in concepts} for c, ps in parents.items()}

    levels, tree_parent = compute_tree(concepts, parents, g)
    alt = defaultdict(set)
    for c in concepts:
        for a in g.objects(c, SKOS.altLabel):
            alt[c].add(str(a))

    rows = []
    for c in sorted(concepts, key=str):
        name = str(g.value(c, SKOS.prefLabel) or str(c).split("#")[-1])
        ps = sorted(parents.get(c, ()), key=lambda p: (levels.get(p, 99), str(p)))
        rows.append({
            "code": str(c),
            "level": levels.get(c),                       # None = detached
            "parent_code": str(tree_parent[c]) if c in tree_parent else None,
            "name": name,
            "alt_labels": sorted(alt[c]),
            "all_parents": [str(p) for p in ps],
        })

    # ---- validate -----------------------------------------------------------
    problems = []
    if len(concepts) != EXPECTED_CONCEPTS:
        problems.append(f"concept count {len(concepts)} != {EXPECTED_CONCEPTS}")
    hist = defaultdict(int)
    for r in rows:
        if r["level"]:
            hist[r["level"]] += 1
    if dict(sorted(hist.items())) != EXPECTED_LEVELS:
        problems.append(f"level histogram {dict(sorted(hist.items()))} != {EXPECTED_LEVELS}")
    codes = {r["code"] for r in rows}
    for r in rows:
        if r["parent_code"] and r["parent_code"] not in codes:
            problems.append(f"dangling parent {r['parent_code']} on {r['code']}")
    if problems:
        sys.exit("VALIDATION FAILED:\n  " + "\n  ".join(problems))

    # ---- multi-parent review file ------------------------------------------
    multi = [r for r in rows if len(r["all_parents"]) > 1]
    MULTI_OUT.parent.mkdir(parents=True, exist_ok=True)
    with MULTI_OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["uri", "name", "level", "parent_code_stored", "all_parents"])
        for r in multi:
            w.writerow([r["code"], r["name"], r["level"] or "", r["parent_code"] or "",
                        " | ".join(r["all_parents"])])

    # ---- write to the DB ----------------------------------------------------
    env = dotenv_values(ROOT / ".env")
    sfx = args.db
    env = {k: env.get(k + sfx, env.get(k)) for k in
           ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")}
    if not all(env.values()):
        sys.exit(f"incomplete DB_*{sfx} credentials in .env")
    conn = psycopg2.connect(host=env["DB_HOST"], port=env["DB_PORT"], dbname=env["DB_NAME"],
                            user=env["DB_USER"], password=env["DB_PASSWORD"], connect_timeout=10)
    try:
        with conn.cursor() as cur:
            # execute_values: one round-trip per batch (~200 rows); plain executemany
            # would take ~0.2s x 1464 statements against the remote DB
            execute_values(
                cur,
                "INSERT INTO validate.soilvoc_types (code, level, parent_code, name, alt_labels) "
                "VALUES %s ON CONFLICT (code) DO UPDATE SET level = EXCLUDED.level, "
                "name = EXCLUDED.name, alt_labels = EXCLUDED.alt_labels, parent_code = NULL",
                [(r["code"], r["level"], None, r["name"], r["alt_labels"]) for r in rows],
                page_size=200)
            execute_values(
                cur,
                "UPDATE validate.soilvoc_types t SET parent_code = v.parent_code "
                "FROM (VALUES %s) AS v(code, parent_code) WHERE t.code = v.code",
                [(r["code"], r["parent_code"]) for r in rows if r["parent_code"]],
                page_size=200)
            cur.execute("""
                SELECT COUNT(*), COUNT(level), COUNT(parent_code), COUNT(alt_labels)
                FROM validate.soilvoc_types""")
            total, with_level, with_parent, with_alt = cur.fetchone()
            cur.execute("SELECT level, COUNT(*) FROM validate.soilvoc_types "
                        "WHERE level IS NOT NULL GROUP BY level ORDER BY level")
            got_hist = dict(cur.fetchall())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"OK: {total} concepts into {env['DB_NAME']}.validate.soilvoc_types "
          f"({with_level} with level, {with_parent} with parent, {with_alt} with alt labels)")
    print(f"level histogram: {got_hist}")
    print(f"multi-parent concepts: {len(multi)} -> {MULTI_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
