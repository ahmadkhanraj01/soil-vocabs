# Usage: python scripts/soilvoc_db_counts.py [--db 1|2]
# Read-only counts: records with subjects/keywords, records with SoilVoc ones, and how many
# unique subjects/keywords are the same as a SoilVoc label (pref or alt, case/space-insensitive).
#   subjects  = subjects table linked via record_subject (split on , ;)
#   keywords  = raw_metadata.subjects + raw_metadata.identification.keywords (original harvested keywords)
#   matched   = raw_metadata.matched_subjects (an existing matching already stored in the DB)
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path
import psycopg2
from dotenv import dotenv_values
from rdflib import Graph, Namespace, RDF
ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument("--db", default="1"); ap.add_argument("--out")
a = ap.parse_args()
e = dotenv_values(ROOT / ".env"); g = lambda k: e[k + a.db]; schema = g("DB_SCHEMA")
assert re.fullmatch(r"\w+", schema)

S = Namespace("http://www.w3.org/2004/02/skos/core#")
G = Graph().parse(ROOT / "SoilVoc.ttl")
norm = lambda x: re.sub(r"\s+", " ", str(x)).strip().lower()
label2c = defaultdict(set)
for c in G.subjects(RDF.type, S.Concept):
    for p in (S.prefLabel, S.altLabel):
        for l in G.objects(c, p): label2c[norm(l)].add(c)
split = lambda x: [norm(t) for t in re.split(r"[;,]", x or "") if norm(t)]

conn = psycopg2.connect(host=g("DB_HOST"), port=g("DB_PORT"), dbname=g("DB_NAME"), user=g("DB_USER"),
                        password=g("DB_PASSWORD"), connect_timeout=30)
conn.set_session(readonly=True); cur = conn.cursor()
cur.execute(f"select count(*) from {schema}.records"); total = cur.fetchone()[0]
cur.execute(f"select rs.record_id, s.label from {schema}.record_subject rs join {schema}.subjects s on s.id = rs.subject_id")
src = {"subjects": defaultdict(set), "keywords": defaultdict(set), "matched_subjects": defaultdict(set)}
raw_labels = set()
for rid, lab in cur.fetchall():
    raw_labels.add(lab); src["subjects"][rid].update(split(lab))
cur.execute(f"""select id, raw_metadata->'subjects', raw_metadata->'identification'->'keywords',
                raw_metadata->'matched_subjects' from {schema}.records""")
def strings(v):
    if isinstance(v, str): yield v
    elif isinstance(v, list):
        for x in v: yield from strings(x)
    elif isinstance(v, dict):
        for x in v.values(): yield from strings(x)
for rid, subj, ident, matched in cur.fetchall():
    for v in (subj, ident):
        for t in strings(v): src["keywords"][rid].update(split(t))
    for t in strings(matched): src["matched_subjects"][rid].update(split(t))
conn.close()

pct = lambda x, y: f"{100*x/y:.1f}%" if y else "-"
res = {}
for name, recs in src.items():
    recs = {r: k for r, k in recs.items() if k}
    uniq = set().union(*recs.values()) if recs else set()
    same = {k for k in uniq if k in label2c}
    rec_sv = {r for r, k in recs.items() if k & same}
    concepts = set().union(*(label2c[k] for k in same)) if same else set()
    res[name] = dict(records=len(recs), records_soilvoc=len(rec_sv), unique=len(uniq), same=len(same), concepts=len(concepts))
anyrec = set(src["subjects"]) | {r for r, k in src["keywords"].items() if k}
anysv = {r for n in ("subjects", "keywords") for r, k in src[n].items() if k & set(label2c)}

L = [f"# Records, subjects and keywords vs SoilVoc", "", f"Database `{g('DB_NAME')}`, schema `{schema}` (read-only). "
     f"Records in total: **{total}**. SoilVoc labels (pref + alt): {len(label2c)}.", "",
     "\"Same as SoilVoc\" = equal to a SoilVoc prefLabel or altLabel, ignoring case and extra spaces "
     "(after splitting on `,` and `;`). No translations, plurals or manual mappings.", "",
     "| Source | Records with it | Records with a SoilVoc one | Unique values | Same as SoilVoc | SoilVoc concepts hit |",
     "|---|---|---|---|---|---|"]
desc = {"subjects": "Subjects (`subjects` table)", "keywords": "Keywords (`raw_metadata` subjects + identification.keywords)",
        "matched_subjects": "`raw_metadata.matched_subjects`"}
for n, r in res.items():
    L.append(f"| {desc[n]} | {r['records']} ({pct(r['records'], total)}) | {r['records_soilvoc']} ({pct(r['records_soilvoc'], total)}) "
             f"| {r['unique']} | {r['same']} ({pct(r['same'], r['unique'])}) | {r['concepts']} of 1464 |")
L.append(f"| Subjects or keywords | {len(anyrec)} ({pct(len(anyrec), total)}) | {len(anysv)} ({pct(len(anysv), total)}) | | | |")
txt = "\n".join(L) + f"\n\nUnique `subjects.label` rows (unsplit): {len(raw_labels)}\n"
print(txt)
if a.out: Path(a.out).write_text(txt)
