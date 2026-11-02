"""Clean the DB subjects into CSV files and link them to SoilVoc. Nothing is written to the DB.

Usage: python scripts/clean_subjects.py [--db 1|2] [--out reports/subjects_cleaned]

Reads (read-only) every subject with its records and the records' language, then for every
subject label:
  1. tidy        lower case, NFKC, spaces, quotes, '#', trailing punctuation
  2. wrapper     'keyword: x', 'name=x' -> 'x'
  3. split       on , ; | and '/' (not inside brackets or numbers like 2,4-d); a part starting with
                 'and'/'or' is joined back ('agriculture, forestry, and fisheries' stays one keyword)
  4. numbering   '15. life on land', '1.5 earth sciences', 'a) x', 'sdg 15: x', '106022 microbiology'
  5. brackets    'geology [science]', 'agriculture (general)' -> without the bracket part
  6. joined      camelCase split, '-', '_', '.' -> space, 'ejp' project prefix
  7. spelling    UK/US and plural forms are tried when matching (the keyword itself is not respelled)
  8. language    to English: manual decisions (curation/keyword_decisions.csv, e.g. boden -> soil),
                 curation/keyword_translations.csv, then the multilingual SoilVoc labels
                 (curation/translated_labels.json)
  9. noise       SDG goals, OECD fields of science and HAL domains (curation/category_labels.csv)
                 are 'category-label'; codes, numbers, dates, links, < 3 characters, curation/stoplist.csv,
                 'noise' decisions
 10. SoilVoc     exact pref/alt label, AGROVOC/GEMET/USDA labels linked by exactMatch/closeMatch,
                 plural/spelling variants, accent-insensitive; 'broader' decisions kept apart
"""
import argparse
import csv
import importlib.util
import re
import runpy
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cmp", ROOT / "scripts" / "compare_subjects_to_soilvoc.py")
cmp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmp)

NUM_PREFIX = re.compile(
    r"^(?:"
    r"sdg\s*\d{1,2}\s*[:.\-–]?\s*"                 # sdg 15: life on land
    r"|goal\s*\d{1,2}\s*[:.\-–]?\s*"               # goal 15 - ...
    r"|\(?\d{1,3}(?:\.\d{1,3})*[.):]?\s+"          # 15. x | 1.5 x | (3) x | 2) x
    r"|\d{4,}\s+"                                  # 106022 microbiology
    r"|[a-z][.)]\s+"                               # a) x | b. x
    r")", re.I)
SCHEME = re.compile(r"^(?:anzsrc(?:\s*for)?|for|msc|jel|vdp|mesh|agrovoc|gemet)\s*:+\s*", re.I)   # anzsrc::4106 soil sciences
CODE_NOISE = [
    re.compile(r"^info\s*:\s*eu"),                                  # info:eu-repo/classification/udc/53
    re.compile(r"^(ddc|udc)\b"),                                      # ddc:631 41
    re.compile(r"^([a-z]+ )?[a-z]{1,5}/[a-z]?\d{4,}/\d+$"),          # grant numbers: nerc ne/l00237/1
    re.compile(r"^(task|subtask|deliverable|wp|work package|milestone)\s*[\d\s.]+$"),
]
BRACKETS = re.compile(r"\s*[\[(][^\])]*[\])]\s*")
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
SEPS = re.compile(r"[-_.\u2010\u2011\u2012\u2013\u2014\u2015\u2212]+")   # incl. typographic dashes


def tidy(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip("\"'`#*•·–- ")
    return s.rstrip(".:;,!?").strip()


def clean_part(raw, uk_us_words):
    """raw part (original casing) -> (cleaned text, [steps applied])."""
    steps = []
    t = tidy(raw)
    w = cmp.WRAPPER_RE.sub("", t)
    if w != t:
        t, _ = tidy(w), steps.append("wrapper")
    if "::" in t or SCHEME.match(t):
        c = tidy(SCHEME.sub("", t.split("::")[-1]))
        c = tidy(re.sub(r":\s*\d+$", "", c))
        if c and c != t:
            t, _ = c, steps.append("classification-code")
    for _ in range(2):  # '1. a) x' has two prefixes
        n = NUM_PREFIX.sub("", t)
        if n != t and n.strip():
            t = tidy(n)
            if "numbering" not in steps:
                steps.append("numbering")
    b = tidy(BRACKETS.sub(" ", t))
    if b != t and b:
        t, _ = b, steps.append("brackets")
    if " " not in t and CAMEL.search(t):
        t, _ = CAMEL.sub(" ", t), steps.append("camelcase")
    low = t.lower()
    s = re.sub(r"\s+", " ", SEPS.sub(" ", low)).strip()
    if s != low and not re.fullmatch(r"[\d\s]+", s):
        low, _ = s, steps.append("separators")
    for pre in cmp.PREFIXES:
        if low.startswith(pre) and len(low) > len(pre) + 2:
            low, _ = low[len(pre):].strip(), steps.append("project-prefix")
    return tidy(low), steps


def split_label(label, quals):
    parts = []
    for seg in re.split(r"\||·|•", label):
        bits = cmp.split_raw(seg)
        # 'agriculture, forestry, and fisheries' is one phrase, not three keywords
        if 1 < len(bits) <= 4 and any(re.match(r"\s*(and|or|&)\s", b, re.I) for b in bits[1:]):
            bits = [seg]
        parts += bits
    out = []
    for p in parts:
        if re.search(r"info\s*:\s*eu|::|\b(ddc|udc)\b", p, re.I):
            out.append(p); continue                   # codes keep their slashes
        bits = [b for b in BRACKETS.sub(" ", p).split("/")]
        if len(bits) > 1 and all(len(tidy(b)) >= 3 for b in bits):
            # 'life sciences [q-bio]/ecology'; drop qualifiers such as 'soil/classification'
            out += [bits[0]] + [b for b in bits[1:] if tidy(b).lower() not in quals]
        else:
            out.append(p)
    return out


def is_noise(t, stop):
    return (any(r.search(t) for r in CODE_NOISE) or cmp.is_noise(t) or t in stop or re.fullmatch(r"[\w-]*\d[\w-]*", t) is not None  # codes like abc123
            or re.fullmatch(r"[a-z]{1,4}\d+.*", t) is not None)


GENERIC_SINGLE = {"soil", "soils", "water", "lead", "building", "inputs", "fragments", "season", "crop", "crops",
                  "root", "roots", "tree", "trees", "ion", "ions", "rock", "rocks", "salt", "salts", "rain", "road",
                  "slope", "organic", "mineral", "minerals"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="1")
    ap.add_argument("--out", default=str(ROOT / "reports" / "subjects_cleaned"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    # --- vocabularies and curation
    concepts, exact = cmp.load_soilvoc()
    mapped = cmp.load_mapped_labels(concepts)
    uk_us = runpy.run_path(str(ROOT / "scripts" / "uk2us.py"))["uk_us"]
    uk_us_words = dict(uk_us)
    exact_u, mapped_u = defaultdict(set), defaultdict(set)
    for k, v in exact.items(): exact_u[cmp.unaccent(k)] |= v
    for k, v in mapped.items(): mapped_u[cmp.unaccent(k)] |= v
    tr_cur, tr_mt = cmp.load_translated(concepts, ROOT / "curation" / "translated_labels.json")
    tr = defaultdict(set)
    for d in (tr_cur, tr_mt):
        for k, v in d.items(): tr[cmp.unaccent(k)] |= v
    decisions = cmp.load_decisions(ROOT / "curation" / "keyword_decisions.csv", concepts)
    stop = {r["word"].strip().lower() for r in cmp.read_csv(ROOT / "curation" / "stoplist.csv")}
    translations = {}
    tpath = ROOT / "curation" / "keyword_translations.csv"
    if tpath.exists():
        for r in cmp.read_csv(tpath):
            translations[cmp.unaccent(r["keyword"].lower())] = (r["english"].lower(), r.get("language", ""))
    catkey = lambda t: re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", cmp.unaccent(t.lower()))).strip()
    cat = {catkey(r["label"]): r["scheme"] for r in cmp.read_csv(ROOT / "curation" / "category_labels.csv")}
    quals = {r["qualifier"].strip().lower() for r in cmp.read_csv(ROOT / "curation" / "path_qualifiers.csv")} | {"classification"}
    levels = {r["uri"]: r for r in csv.DictReader(open(ROOT / "reports" / "soilvoc_keywords_by_level.csv"))}
    # SoilVoc labels that may be found INSIDE a longer keyword ('sustainable soil management').
    # Single words only if they are specific (level 3+) and not everyday words.
    toks = lambda t: tuple(re.findall(r"[a-z0-9]+", cmp.unaccent(t.lower())))
    lvl = lambda u: int(levels[u]["level"]) if levels.get(u, {}).get("level") else 0
    inside = defaultdict(set)
    for lab, ids in exact.items():
        tk = toks(lab)
        if not tk: continue
        ok = {u for u in ids if len(tk) >= 2 or (lvl(u) >= 3 and tk[0] not in GENERIC_SINGLE and len(tk[0]) > 3)}
        for f in {tk, tk[:-1] + (tk[-1] + "s",)} | ({tk[:-1] + (tk[-1][:-1],)} if tk[-1].endswith("s") and len(tk[-1]) > 4 else set()):
            inside[f] |= ok
    maxn = max(len(k) for k in inside)

    def contains(t):
        tk = toks(t); found = []
        for i in range(len(tk)):
            for n in range(maxn, 0, -1):
                if i + n <= len(tk) and inside.get(tk[i:i + n]):
                    found.append((i, i + n, inside[tk[i:i + n]])); break
        # keep only the longest matches (drop 'soil management' inside 'sustainable soil management' duplicates)
        keep = [f for f in found if not any(g[0] <= f[0] and f[1] <= g[1] and g != f for g in found)]
        return set().union(*(f[2] for f in keep)) if keep else set()

    def soilvoc(t):
        """english keyword -> (relation, concept ids)."""
        if t in exact: return "exact", exact[t]
        if t in mapped: return "mapped", mapped[t]
        for v in cmp.spelling_variants(t, uk_us):
            if v in exact: return "variant", exact[v]
            if v in mapped: return "variant", mapped[v]
        u = cmp.unaccent(t)
        if u in exact_u: return "accents", exact_u[u]
        if u in mapped_u: return "mapped", mapped_u[u]
        return "", set()

    # --- data (read-only)
    e = dotenv_values(ROOT / ".env"); g = lambda k: e[k + a.db]; schema = g("DB_SCHEMA")
    assert re.fullmatch(r"\w+", schema)
    conn = psycopg2.connect(host=g("DB_HOST"), port=g("DB_PORT"), dbname=g("DB_NAME"), user=g("DB_USER"),
                            password=g("DB_PASSWORD"), connect_timeout=30)
    conn.set_session(readonly=True); cur = conn.cursor()
    cur.execute(f"""select s.id, s.label, rs.record_id, r.language from {schema}.subjects s
        left join {schema}.record_subject rs on rs.subject_id = s.id
        left join {schema}.records r on r.id = rs.record_id""")
    data = cur.fetchall()
    cur.execute(f"select count(*) from {schema}.records"); total = cur.fetchone()[0]
    conn.close()
    subj = {}; recs = defaultdict(set); langs = defaultdict(Counter)
    for sid, label, rid, lang in data:
        subj[sid] = label or ""
        if rid:
            recs[sid].add(rid); langs[sid][lang or "unknown"] += 1

    # --- clean
    rows = []; rec_concepts = defaultdict(set); rec_concepts_strict = defaultdict(set); rec_partial = defaultdict(set)
    for sid, label in subj.items():
        rec_lang = langs[sid].most_common(1)[0][0] if langs[sid] else "unknown"
        parts = split_label(label, quals)
        split = len([p for p in parts if tidy(p)]) > 1
        for raw in parts:
            if not tidy(raw):
                continue
            cleaned, steps = clean_part(raw, uk_us_words)
            if split: steps.insert(0, "split")
            english, lang, relation, ids, status = cleaned, "", "", set(), "unclassified"
            key = cmp.unaccent(cleaned)
            dec = decisions.get(cleaned) or decisions.get(cmp.norm(raw))
            uuidlike = re.fullmatch(r"[0-9a-f]{8}[\s-][0-9a-f]{4}[\s-][0-9a-f]{4}[\s-][0-9a-f]{4}[\s-][0-9a-f]{12}", cleaned)
            if uuidlike or any(r.search(cleaned) for r in CODE_NOISE) or (dec and dec["decision"] == "noise"):
                status = "noise"
            else:
                if dec and dec["decision"] in ("synonym", "broader"):
                    ids = {dec["target_concept_uri"]}; relation = dec["decision"]
                    english = concepts[dec["target_concept_uri"]]["label"].lower()
                    if english != cleaned and not soilvoc(cleaned)[0]:
                        steps.append("language/synonym (manual decision)")
                elif key in translations:
                    english, lang = translations[key]; steps.append("language (keyword_translations.csv)")
                rel2, ids2 = soilvoc(english)
                if not ids and ids2:
                    relation, ids = rel2, ids2
                if not ids and key in tr:
                    hit = tr[key]; ids = {i for i, _ in hit}; relation = "translation"
                    lang = ",".join(sorted({l for _, l in hit}))
                    english = "; ".join(sorted(concepts[i]["label"].lower() for i in ids))
                    steps.append("language (SoilVoc translated labels)")
                if ids:
                    status = "soilvoc" if len(ids) == 1 else "soilvoc-ambiguous"
                elif catkey(cleaned) in cat or catkey(english) in cat:
                    status = "category-label"; steps.append(cat.get(catkey(cleaned)) or cat[catkey(english)])
                elif is_noise(cleaned, stop):
                    status = "noise"
                elif dec and dec["decision"] == "new_term":
                    status = "proposed-new-term"
                elif len(toks(english)) >= 2 and contains(english):
                    ids = contains(english); status = "soilvoc-partial"; relation = "contains"
                    steps.append("SoilVoc term inside keyword")
            if not lang:
                lang = rec_lang
            for rid in recs[sid]:
                if status == "soilvoc-partial":
                    rec_partial[rid] |= ids
                elif status.startswith("soilvoc"):
                    rec_concepts[rid] |= ids
                    if relation != "broader" and status == "soilvoc":
                        rec_concepts_strict[rid] |= ids
            rows.append(dict(subject_id=sid, original_label=label, part=tidy(raw), cleaned=cleaned,
                             english=english, language=lang, cleaning_steps="; ".join(steps), status=status,
                             relation=relation, soilvoc_label="; ".join(sorted(concepts[i]["label"] for i in ids)),
                             soilvoc_level="; ".join(sorted(levels.get(i, {}).get("level", "") or "-" for i in ids)),
                             soilvoc_uri="; ".join(sorted(ids)), records=len(recs[sid])))

    with open(out / "subjects_cleaned.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(out / "record_soilvoc.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["record_id", "soilvoc_uri", "soilvoc_label", "level", "link"])
        for rid in sorted(set(rec_concepts) | set(rec_partial), key=str):
            full, strict, part = rec_concepts.get(rid, set()), rec_concepts_strict.get(rid, set()), rec_partial.get(rid, set())
            for u in sorted(full | part):
                link = "full" if u in strict else "broader/ambiguous" if u in full else "inside a longer keyword"
                w.writerow([rid, u, concepts[u]["label"], levels.get(u, {}).get("level", ""), link])

    # --- numbers
    uniq = {}
    for r in rows: uniq.setdefault(r["cleaned"], r)
    st = Counter(r["status"] for r in uniq.values())
    raw_uniq = len({cmp.norm(p) for l in subj.values() for p in cmp.split_raw(l) if cmp.norm(p)})
    steps_c = Counter(s for r in rows for s in r["cleaning_steps"].split("; ") if s)
    rel_c = Counter(r["relation"] for r in uniq.values() if r["status"] == "soilvoc")
    with_subj = len({rid for s in recs.values() for rid in s})
    exact_before = {rid for sid, l in subj.items() for rid in recs[sid]
                    if any(cmp.norm(p) in exact for p in cmp.split_raw(l))}
    concepts_used = set().union(*rec_concepts.values()) if rec_concepts else set()
    concepts_strict = set().union(*rec_concepts_strict.values()) if rec_concepts_strict else set()
    concepts_all = concepts_used | (set().union(*rec_partial.values()) if rec_partial else set())
    recs_all = set(rec_concepts) | set(rec_partial)
    pct = lambda x, y: f"{100 * x / y:.1f}%" if y else "-"
    lang_c = Counter(r["language"] for r in uniq.values() if r["status"] == "unclassified")
    top_unc = Counter()
    for r in rows:
        if r["status"] == "unclassified": top_unc[r["cleaned"]] += r["records"]
    L = [f"# Cleaned subjects vs SoilVoc", "",
         f"Database `{g('DB_NAME')}`, schema `{schema}` (read-only). Cleaning is done in CSV only; nothing is written to the DB.", "",
         "## Result", "",
         f"- SoilVoc concepts used by records: **{len(concepts_used)} of {len(concepts)}** "
         f"({len(concepts_strict)} without 'broader' links)",
         f"- Records with a SoilVoc subject: **{len(rec_concepts)} of {total} ({pct(len(rec_concepts), total)})**, "
         f"{pct(len(rec_concepts), with_subj)} of the {with_subj} records with subjects "
         f"({len(rec_concepts_strict)} without 'broader' links)",
         f"- Before cleaning (exact labels only): {len(exact_before)} records",
         f"- Including SoilVoc terms found inside longer keywords (weaker): {len(concepts_all)} concepts, "
         f"{len(recs_all)} records ({pct(len(recs_all), total)})", "",
         "## Keywords", "",
         f"- Unique keywords before cleaning: {raw_uniq}",
         f"- Unique keywords after cleaning: {len(uniq)}",
         f"- SoilVoc: {st['soilvoc']} (exact {rel_c['exact']}, synonym {rel_c['synonym']}, translation {rel_c['translation']}, "
         f"variant {rel_c['variant']}, mapped {rel_c['mapped']}, accents {rel_c['accents']}, broader {rel_c['broader']})",
         f"- SoilVoc but ambiguous (more than one concept): {st['soilvoc-ambiguous']}",
         f"- SoilVoc term inside a longer keyword (weaker link): {st['soilvoc-partial']}",
         f"- Proposed new SoilVoc terms: {st['proposed-new-term']}",
         f"- Category labels (SDG goals, OECD fields of science, HAL domains, INSPIRE themes, portal tags): {st['category-label']}",
         f"- Noise: {st['noise']}",
         f"- Not yet classified: {st['unclassified']}", "",
         "## Cleaning steps applied (keyword parts)", ""] + [f"- {k}: {v}" for k, v in steps_c.most_common()] + [
         "", "## Not yet classified, by record language (unique keywords)", ""] + [
         f"- {k}: {v}" for k, v in lang_c.most_common(8)] + [
         "", "## Top 40 not yet classified keywords (by records)", ""] + [
         f"- {k} ({v})" for k, v in top_unc.most_common(40)] + [
         "", "## Files", "",
         "- `subjects_cleaned.csv`: one row per subject part: original, cleaned, English, language, steps, status, SoilVoc concept",
         "- `record_soilvoc.csv`: one row per record and SoilVoc concept",
         "", "Language is the translation's language when one was used, otherwise the most common language of the subject's records."]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:30]))


if __name__ == "__main__":
    main()
