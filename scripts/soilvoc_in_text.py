# Usage: python scripts/soilvoc_in_text.py [--db 1|2] [--out reports/soilvoc_in_title_abstract]
# Read-only. Finds SoilVoc labels (pref + alt) in every record's title and abstract.
# Matching: lower case, whole words, hyphens/punctuation treated as spaces, plus a simple
# singular/plural variant of the last word ("soil type" <-> "soil types"). Labels under 3
# characters are skipped. English labels only, so non-English abstracts are under-counted.
import argparse, csv, re
from collections import defaultdict, Counter
from pathlib import Path
import psycopg2
from dotenv import dotenv_values
from rdflib import Graph, Namespace, RDF
ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument("--db", default="1")
ap.add_argument("--out", default=str(ROOT / "reports" / "soilvoc_in_title_abstract")); a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
e = dotenv_values(ROOT / ".env"); g = lambda k: e[k + a.db]; schema = g("DB_SCHEMA")
assert re.fullmatch(r"\w+", schema)

tok = lambda s: re.findall(r"[a-z0-9]+", (s or "").lower())
S = Namespace("http://www.w3.org/2004/02/skos/core#")
G = Graph().parse(ROOT / "SoilVoc.ttl")
lv = {r["uri"]: r for r in csv.DictReader(open(ROOT / "reports" / "soilvoc_keywords_by_level.csv"))}
phrase2c = defaultdict(set); skipped = set()
for c in G.subjects(RDF.type, S.Concept):
    for p in (S.prefLabel, S.altLabel):
        for l in G.objects(c, p):
            t = tok(str(l))
            if not t or len(" ".join(t)) < 3: skipped.add(str(l)); continue
            forms = {tuple(t)}
            w = t[-1]
            if w.isalpha() and len(w) > 3:
                forms.add(tuple(t[:-1] + [w + "s"]))
                if w.endswith("s") and not w.endswith("ss"): forms.add(tuple(t[:-1] + [w[:-1]]))
            for f in forms: phrase2c[f].add(str(c))
maxn = max(len(p) for p in phrase2c)
# Everyday English words that are SoilVoc labels but rarely mean the soil concept in abstracts
# ("lead" the verb, "building on", "inputs" in general). Counted per concept but flagged and
# left out of record-level results.
AMBIGUOUS = {"lead", "building", "inputs", "fragments"}
amb_uris = {str(c) for c in G.subjects(RDF.type, S.Concept)
            if str(G.value(c, S.prefLabel) or "").lower() in AMBIGUOUS}

def find(text):
    t = tok(text); hits = set()
    for i in range(len(t)):
        for n in range(1, maxn + 1):
            if i + n > len(t): break
            hits |= phrase2c.get(tuple(t[i:i + n]), set())
    return hits

conn = psycopg2.connect(host=g("DB_HOST"), port=g("DB_PORT"), dbname=g("DB_NAME"), user=g("DB_USER"),
                        password=g("DB_PASSWORD"), connect_timeout=30)
conn.set_session(readonly=True); cur = conn.cursor()
cur.execute(f"""select r.id, r.title, r.abstract, r.language,
    exists(select 1 from {schema}.record_subject rs where rs.record_id = r.id) from {schema}.records r""")
recs = cur.fetchall(); conn.close()

level = lambda u: int(lv[u]["level"]) if lv.get(u, {}).get("level") else 0
label = lambda u: lv[u]["prefLabel"] if u in lv else u
c_title, c_abs, c_any, c_nosub = Counter(), Counter(), Counter(), Counter()
rows = []; n_any = n_nosub = n_nosub_hit = n_text = 0
for rid, title, abstract, lang, has_sub in recs:
    th_all, ah_all = find(title), find(abstract)
    for u in th_all & amb_uris: c_title[u] += 1
    for u in ah_all & amb_uris: c_abs[u] += 1
    for u in (th_all | ah_all) & amb_uris:
        c_any[u] += 1; c_nosub[u] += not has_sub
    th, ah = th_all - amb_uris, ah_all - amb_uris
    allh = th | ah
    if (title or "").strip() or (abstract or "").strip(): n_text += 1
    if not has_sub: n_nosub += 1
    for u in th: c_title[u] += 1
    for u in ah: c_abs[u] += 1
    for u in allh:
        c_any[u] += 1
        if not has_sub: c_nosub[u] += 1
    if allh:
        n_any += 1; n_nosub_hit += not has_sub
        deep = max(level(u) for u in allh)
        rows.append([rid, "yes" if has_sub else "no", lang or "", len(allh), deep,
                     "; ".join(sorted(label(u) for u in allh if level(u) == deep)),
                     "; ".join(sorted(label(u) for u in th)), "; ".join(sorted(label(u) for u in ah))])
    else:
        rows.append([rid, "yes" if has_sub else "no", lang or "", 0, "", "", "", ""])

with open(out / "record_hits.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["record_id", "has_subjects", "language", "n_concepts", "deepest_level",
                                   "deepest_concepts", "concepts_in_title", "concepts_in_abstract"]); w.writerows(rows)
with open(out / "concept_hits.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["level", "prefLabel", "top_concept", "records_title", "records_abstract",
                                   "records_any", "records_without_subjects", "ambiguous_word", "uri"])
    for u in sorted(lv, key=lambda u: -c_any[u]):
        r = lv[u]; w.writerow([r["level"], r["prefLabel"], r["top_concept"], c_title[u], c_abs[u], c_any[u], c_nosub[u], "yes" if u in amb_uris else "", u])

pct = lambda x, y: f"{100*x/y:.1f}%" if y else "-"
total = len(recs); found = sum(1 for u in lv if c_any[u])
by_level = defaultdict(lambda: [0, 0])
for u, r in lv.items():
    k = r["level"] or "detached"; by_level[k][0] += 1; by_level[k][1] += bool(c_any[u])
deep_dist = Counter(r[4] for r in rows if r[3])
GENERIC = 0.10
generic = [u for u in lv if c_any[u] / total >= GENERIC]
L = ["# SoilVoc terms in record titles and abstracts", "",
     f"Database `{g('DB_NAME')}`, schema `{schema}` (read-only). Matching: whole words, case-insensitive, "
     "simple singular/plural, English SoilVoc labels only. Labels under 3 characters skipped: " + ", ".join(sorted(skipped)) + ".", "",
     "## Records", "",
     f"- Records in total: {total} ({n_text} with a title or abstract)",
     f"- Records with at least one SoilVoc term in title or abstract: **{n_any} ({pct(n_any, total)})**",
     f"- Records without subjects: {n_nosub}; of these, {n_nosub_hit} ({pct(n_nosub_hit, n_nosub)}) contain a SoilVoc term",
     "- Deepest SoilVoc level found per record (deeper = more specific term): " +
     ", ".join(f"level {k}: {deep_dist[k]}" for k in sorted(deep_dist)), "",
     "## SoilVoc concepts", "",
     f"- Concepts found in at least one record: **{found} of {len(lv)} ({pct(found, len(lv))})**",
     ] + [f"- Level {k}: {v[1]} of {v[0]} found ({pct(v[1], v[0])})" for k, v in sorted(by_level.items(), key=lambda kv: (kv[0] == 'detached', kv[0]))] + [
     "", f"## Very common terms (in {int(GENERIC*100)}% or more of records)", "",
     "These are too general to say much on their own; a record is better described by its deepest terms.", ""] + [
     f"- {label(u)} (level {lv[u]['level']}): {c_any[u]} records" for u in sorted(generic, key=lambda u: -c_any[u])] + [
     "", "## Most found concepts (top 30)", ""] + [
     f"- {label(u)} (level {lv[u]['level'] or '-'}, {lv[u]['top_concept'] or 'detached'}): {c_any[u]} records "
     f"(title {c_title[u]}, abstract {c_abs[u]}, without subjects {c_nosub[u]})"
     for u in sorted(lv, key=lambda u: -c_any[u])[:30]] + [
     "", "## Files", "",
     "- `concept_hits.csv`: per SoilVoc concept, how many records mention it in title, abstract, either, and among records without subjects",
     "- `record_hits.csv`: per record, the SoilVoc concepts found in title and abstract and the deepest (most specific) ones",
     "", "## Limits", "",
     "- Only English labels: German, Italian, Dutch etc. abstracts are under-counted.",
     "- A word match is not meaning: \"soil\" in \"we did not sample soil\" still counts; very general terms (soil, water, climate) match almost everything.",
     "- FAO, WRB and USDA versions of the same soil type (e.g. Luvisols) are separate concepts, so one mention counts for each.",
     "- These are suggestions for records, not checked subjects."]
(out / "report.md").write_text("\n".join(L) + "\n")
print("\n".join(L[:40]))
