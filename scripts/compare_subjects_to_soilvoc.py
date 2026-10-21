"""Compare the unique subject keywords in the database with SoilVoc (report only).

Read-only: it runs SELECTs and writes CSV/Markdown files to --out. Nothing is
written to the database.

Credentials come from .env (DB_HOST1 ... DB_SCHEMA1, or the unnumbered names).

Match tiers, first hit wins:
  exact    keyword equals a SoilVoc prefLabel or altLabel
  mapped   keyword equals a label of an AGROVOC/GEMET/NALT/... concept that
           SoilVoc links through exactMatch or closeMatch
  variant  keyword equals a SoilVoc label after a plural or UK->US spelling change
  none     no match
No LLM and no fuzzy scoring are used.

Run: python scripts/compare_subjects_to_soilvoc.py [--out reports/subjects_vs_soilvoc]
"""
import argparse
import csv
import json
import re
import runpy
import unicodedata
from collections import defaultdict
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SEP_RE = re.compile(r"[,;]")
MATCH_TIERS = ("exact", "mapped", "variant", "normalised", "normalised_path", "normalised_prefix", "manual")
# translated labels are only suggestions (some are wrong, e.g. it. emergenza = emergency): shown, but not counted in the headline numbers
REVIEW_TIERS = ("translated_curated", "translated_mt")
DECISIONS = ("synonym", "broader", "new_term", "noise", "skip")
DECISION_COLS = ["keyword", "decision", "target_concept_uri", "new_term_label", "notes"]
SHEET_COLS = ["keyword", "records", "example_raw_labels", "suggested_concept_uri",
              "suggested_concept_label", "decision", "target_concept_uri", "new_term_label", "notes"]
GENERIC = {"soil", "of", "and", "the", "in", "for", "on", "to", "a", "by", "with"}
PREFIXES = ("ejp",)
QUALIFIERS = set()
WRAPPER_RE = re.compile(r"^(name|keyword|keywords|subject|tag|theme|topic)\s*[=:]\s*", re.I)


def load_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")
    return env


def norm(s):
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    s = s.strip("\"'`#")
    return s.rstrip(".:").strip()


def split_raw(label):
    """Split on , or ; but not inside brackets or between digits (e.g. 2,2'-)."""
    parts, depth, cur = [], 0, []
    for i, ch in enumerate(label):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            prev_c = label[i - 1] if i else ""
            next_c = label[i + 1] if i + 1 < len(label) else ""
            if not (ch == "," and prev_c.isdigit() and next_c.isdigit()):
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def split_keywords(label):
    return [p for p in (norm(p) for p in split_raw(label)) if p]


def unaccent(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def is_noise(t):
    return (
        len(t) < 3
        or re.fullmatch(r"[\d\W_]+", t) is not None
        or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27}", t) is not None
        or t.startswith(("http://", "https://"))
        or re.match(r"^\d{4}-\d{2}-\d{2}", t) is not None
        or re.match(r"^\d{1,4}\.? ", t) is not None  # SDG / OECD field labels
    )


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            yield {k.strip(): (v or "").strip() for k, v in row.items() if k and isinstance(v, str) or (k and v is None)}


def split_list(v):
    return [x.strip() for x in v.split(" | ") if x.strip()]


def load_soilvoc():
    concepts, label_to_ids = {}, defaultdict(set)
    for r in read_csv(ROOT / "SoilVoc_concepts.csv"):
        cid = r["id"]
        concepts[cid] = {
            "label": r["prefLabel"],
            "type": r["type"],
            "matches": split_list(r["exactMatch"]) + split_list(r["closeMatch"]),
        }
        for lab in [r["prefLabel"]] + split_list(r["altLabel"]):
            if norm(lab):
                label_to_ids[norm(lab)].add(cid)
    return concepts, label_to_ids


def load_mapped_labels(concepts):
    """label -> SoilVoc concept ids, through exactMatch/closeMatch URIs."""
    uri_to_ids = defaultdict(set)
    for cid, c in concepts.items():
        for u in c["matches"]:
            uri_to_ids[u].add(cid)
    mapped = defaultdict(set)
    for csv_path in (ROOT / "ontovocabs").rglob("*.csv"):
        try:
            for r in read_csv(csv_path):
                ids = uri_to_ids.get(r.get("concept", ""))
                if not ids:
                    continue
                for lab in [r.get("prefLabel", "")] + r.get("altLabels", "").split(";"):
                    if norm(lab):
                        mapped[norm(lab)] |= ids
        except KeyError:
            continue
    return mapped


def spelling_variants(t, uk_us):
    out = {t}
    for uk, us in uk_us:
        if uk in t:
            out.add(t.replace(uk, us))
        if us in t:
            out.add(t.replace(us, uk))
    more = set()
    for v in out:
        if v.endswith("ies"):
            more.add(v[:-3] + "y")
        elif v.endswith("es"):
            more.add(v[:-2])
        if v.endswith("s"):
            more.add(v[:-1])
        else:
            more.add(v + "s")
    return (out | more) - {t}


def rule_candidates(t, raw):
    """Cleaned forms of a keyword: (rule, tier, text). Applied only after the plain tiers fail."""
    out = []
    # A2 camel-case, on the original casing
    if re.search(r"[a-z0-9][A-Z]", raw):
        out.append(("A2", "normalised", norm(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw))))
    # A3 wrappers such as name=... or keyword: ...
    w = WRAPPER_RE.sub("", t).lstrip("#").strip()
    if w != t:
        out.append(("A3", "normalised", norm(w)))
    # A4 bracketed codes such as [sdv.sa.sds]
    b = norm(re.sub(r"\[[^\]]*\]", " ", t))
    if b != t:
        out.append(("A4", "normalised", b))
    # A1 separators between words
    s1 = norm(re.sub(r"[-_.]+", " ", t))
    if s1 != t:
        out.append(("A1", "normalised", s1))
    # A7 project prefix, e.g. "ejp soil" or "ejpsoil"
    for pre in PREFIXES:
        if t.startswith(pre) and len(t) > len(pre) + 2:
            out.append(("A7", "normalised_prefix", norm(t[len(pre):])))
    # A5 "topic/qualifier" paths such as "microplastics/analysis": match the topic
    # only when every later part is a known qualifier (curation/path_qualifiers.csv)
    if "/" in t:
        parts = [norm(p) for p in t.split("/")]
        if len(parts) > 1 and parts[0] and all(p in QUALIFIERS for p in parts[1:]):
            out.append(("A5", "normalised_path", parts[0]))
            out.append(("A5", "normalised_path", norm(re.sub(r"\[[^\]]*\]", " ", parts[0]))))
    return out


def match(t, exact, mapped, uk_us, raw="", exact_u=None, mapped_u=None, stop=frozenset(), tr_cur_u=None, tr_mt_u=None):
    """Returns (tier, ids, rule, cleaned)."""
    if t in exact:
        return "exact", exact[t], "", ""
    if t in mapped:
        return "mapped", mapped[t], "", ""
    for v in spelling_variants(t, uk_us):
        if v in exact:
            return "variant", exact[v], "", ""
        if v in mapped:
            return "variant", mapped[v], "", ""
    if exact_u is None:
        return "none", set(), "", ""
    # A6: accent-insensitive comparison for the keyword itself and every cleaned form
    cands = [("A6", "normalised", t)] + rule_candidates(t, raw or t)
    for rule, tier, text in cands:
        if len(text) < 3 or text in stop or is_noise(text):
            continue
        key = unaccent(text)
        if rule != "A6" and text in exact:
            return tier, exact[text], rule, text
        if rule != "A6" and text in mapped:
            return tier, mapped[text], rule, text
        if key in exact_u:
            return tier, exact_u[key], rule if rule != "A6" or key != t else "A6", text
        if key in mapped_u:
            return tier, mapped_u[key], rule, text
    # last resort: translated labels (exact, accent-insensitive), suggestions only
    if len(t) >= 3 and t not in stop:
        for tier, tr in (("translated_curated", tr_cur_u), ("translated_mt", tr_mt_u)):
            hit = (tr or {}).get(unaccent(t))
            if hit:
                langs = ",".join(sorted({l for _, l in hit}))
                if len({i for i, _ in hit}) > 1:
                    tier = "translated_mt"  # ambiguous translation: suggest only
                return tier, {i for i, _ in hit}, "translated:" + langs, t
    return "none", set(), "", ""


def load_translated(concepts, path):
    """Non-English labels from curation/translated_labels.json (built by soilwise-he/metadata-augmentation).
    Returns (curated, machine): label -> {(concept id, language)}. Only labels of concepts in SoilVoc_concepts.csv."""
    curated, machine = defaultdict(set), defaultdict(set)
    if not Path(path).exists():
        return curated, machine
    with open(path, encoding="utf-8") as f:
        for c in json.load(f):
            cid = c.get("identifier")
            if cid not in concepts:
                continue
            for lang, labels in c.get("labels", {}).items():
                if lang == "en":
                    continue
                target = curated if c.get("label_sources", {}).get(lang) == "curated" else machine
                for lab in labels:
                    k = norm(lab)
                    if len(k) >= 3:
                        target[k].add((cid, lang))
    return curated, machine


def validate_decision(r, concepts, where):
    d = r.get("decision", "").strip().lower()
    target = r.get("target_concept_uri", "").strip()
    label = r.get("new_term_label", "").strip()
    if d not in DECISIONS:
        raise SystemExit(f"{where}: keyword '{r.get('keyword')}': decision '{d}' is not one of {DECISIONS}")
    if target and target not in concepts:
        raise SystemExit(f"{where}: keyword '{r.get('keyword')}': target_concept_uri is not in SoilVoc_concepts.csv")
    if d in ("synonym", "broader") and not target:
        raise SystemExit(f"{where}: keyword '{r.get('keyword')}': {d} needs target_concept_uri")
    if d == "new_term" and not label:
        raise SystemExit(f"{where}: keyword '{r.get('keyword')}': new_term needs new_term_label")
    return {"keyword": norm(r["keyword"]), "decision": d, "target_concept_uri": target,
            "new_term_label": label, "notes": r.get("notes", "").strip()}


def load_decisions(path, concepts):
    out = {}
    if not path.exists():
        return out
    for r in read_csv(path):
        row = validate_decision(r, concepts, path.name)
        old = out.get(row["keyword"])
        if old and old != row:
            raise SystemExit(f"{path.name}: keyword '{row['keyword']}' is decided twice with different results")
        out[row["keyword"]] = row
    return out


def import_sheet(sheet, decisions_path, concepts):
    """Merge decisions filled in review_sheet.csv into keyword_decisions.csv (validated first)."""
    decisions = load_decisions(decisions_path, concepts)
    if not sheet.exists():
        return decisions, 0
    new = 0
    for r in read_csv(sheet):
        if not r.get("decision", "").strip():
            continue
        row = validate_decision(r, concepts, sheet.name)
        old = decisions.get(row["keyword"])
        if old and old != row:
            raise SystemExit(
                f"{sheet.name}: keyword '{row['keyword']}' already has a different decision in "
                f"{decisions_path.name}; edit that file instead")
        if not old:
            decisions[row["keyword"]] = row
            new += 1
    if new:
        write_csv(decisions_path, DECISION_COLS,
                  [[d[c] for c in DECISION_COLS] for _, d in sorted(decisions.items())])
    return decisions, new


def tokens(text):
    out = set()
    for w in re.findall(r"[a-z0-9]+", unaccent(text.lower())):
        w = w[:-1] if len(w) > 3 and w.endswith("s") else w
        if w not in GENERIC:
            out.add(w)
    return out


def build_suggester(exact, concepts):
    label_tokens = {lab: tokens(lab) for lab in exact}
    index = defaultdict(list)
    for lab, toks in label_tokens.items():
        for tk in toks:
            index[tk].append(lab)

    def suggest(keyword):
        kt = tokens(keyword)
        cand = {lab for tk in kt for lab in index.get(tk, ())}
        best = None
        for lab in cand:
            lt = label_tokens[lab]
            score = len(kt & lt) / len(kt | lt)
            key = (-score, len(lab), lab)
            if best is None or key < best[0]:
                best = (key, lab)
        if not best:
            return "", ""
        cid = sorted(exact[best[1]])[0]
        return cid, concepts[cid]["label"]

    return suggest


def fetch_subjects(env):
    sfx = "1" if "DB_HOST1" in env else ""
    g = lambda k: env[k + sfx]
    schema = env.get("DB_SCHEMA" + sfx, "public")
    if not re.fullmatch(r"\w+", schema):
        raise SystemExit("bad schema name")
    conn = psycopg2.connect(
        host=g("DB_HOST"), port=g("DB_PORT"), dbname=g("DB_NAME"),
        user=g("DB_USER"), password=g("DB_PASSWORD"), connect_timeout=10,
    )
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cur.execute(
        f"select s.label, rs.record_id from {schema}.subjects s "
        f"left join {schema}.record_subject rs on rs.subject_id = s.id"
    )
    rows = cur.fetchall()
    cur.execute(f"select count(*) from {schema}.records")
    n_records = cur.fetchone()[0]
    conn.close()
    return g("DB_NAME"), schema, rows, n_records


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT / ".env"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "subjects_vs_soilvoc"))
    ap.add_argument("--curation-dir", default=str(ROOT / "curation"))
    ap.add_argument("--top", type=int, default=500, help="rows in the review sheet")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    uk_us = runpy.run_path(str(ROOT / "scripts" / "uk2us.py"))["uk_us"]
    concepts, exact = load_soilvoc()
    mapped = load_mapped_labels(concepts)
    db_name, schema, rows, n_records = fetch_subjects(load_env(args.env))

    cur_dir = Path(args.curation_dir)
    cur_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = cur_dir / "review_sheet.csv"
    decisions_path = cur_dir / "keyword_decisions.csv"
    decisions, n_imported = import_sheet(sheet_path, decisions_path, concepts)

    def fold(d):
        out_d = defaultdict(set)
        for k, v in d.items():
            out_d[unaccent(k)] |= v
        return out_d

    exact_u, mapped_u = fold(exact), fold(mapped)
    tr_cur, tr_mt = load_translated(concepts, ROOT / "curation" / "translated_labels.json")

    def fold_tr(d):
        out_d = defaultdict(set)
        for k, v in d.items():
            out_d[unaccent(k)] |= v
        return out_d

    # a translated label that is already a SoilVoc label is not new information
    tr_cur_u = {k: v for k, v in fold_tr(tr_cur).items() if k not in exact_u and k not in mapped_u}
    tr_mt_u = {k: v for k, v in fold_tr(tr_mt).items() if k not in exact_u and k not in mapped_u and k not in tr_cur_u}
    stop_path = ROOT / "curation" / "stoplist.csv"
    q_path = ROOT / "curation" / "path_qualifiers.csv"
    if q_path.exists():
        QUALIFIERS.update(norm(r["qualifier"]) for r in read_csv(q_path))
    stop = {norm(r["word"]) for r in read_csv(stop_path)} if stop_path.exists() else set()

    # keyword -> set of record ids, and the raw labels it came from
    recs, sources, raw_of = defaultdict(set), defaultdict(set), {}
    raw_labels = defaultdict(set)
    for label, rid in rows:
        whole = norm(label or "")
        # classification labels such as "0401 agriculture, forestry, and fisheries"
        # contain commas but are one value, so they are not split
        if whole and is_noise(whole):
            pairs = [(whole, whole)]
        else:
            pairs = [(norm(p), p.strip()) for p in split_raw(label or "") if norm(p)]
        for t, raw in pairs:
            raw_of.setdefault(t, raw)
            if label and len(raw_labels[t]) < 3:
                raw_labels[t].add(label)
            if rid:
                recs[t].add(rid)
            else:
                recs.setdefault(t, set())
            if t != norm(label or ""):
                sources[t].add(label)
    keywords = sorted(recs)

    res = {}
    for t in keywords:
        noise = is_noise(t)
        dec = decisions.get(t)
        if dec and dec["decision"] in ("synonym", "broader"):
            res[t] = ("manual", {dec["target_concept_uri"]}, dec["decision"], t)
        elif dec and dec["decision"] == "noise":
            res[t] = ("noise", set(), "", "")
        elif noise:
            res[t] = ("noise", set(), "", "")
        else:
            res[t] = match(t, exact, mapped, uk_us, raw_of.get(t, t), exact_u, mapped_u, stop, tr_cur_u, tr_mt_u)
            # a human decision (new_term, skip) beats a suggestion from translated labels
            if dec and res[t][0].startswith("translated"):
                res[t] = ("none", set(), "", "")

    def concept_cols(ids):
        ids = sorted(ids)
        return (
            " | ".join(concepts[i]["label"] for i in ids),
            " | ".join(ids),
            " | ".join(sorted({concepts[i]["type"] for i in ids})),
        )

    matched_rows, unmatched_rows, noise_rows = [], [], []
    for t in keywords:
        tier, ids, rule, cleaned = res[t]
        n = len(recs[t])
        if tier in MATCH_TIERS or tier in REVIEW_TIERS:
            matched_rows.append([t, tier, n, *concept_cols(ids), rule, cleaned])
        elif tier == "none":
            unmatched_rows.append([t, n, " | ".join(sorted(sources[t]))[:200]])
        else:
            noise_rows.append([t, n])
    mt_kw = [t for t in keywords if res[t][0] in REVIEW_TIERS]
    matched_rows.sort(key=lambda r: -r[2])
    unmatched_rows.sort(key=lambda r: -r[1])
    noise_rows.sort(key=lambda r: -r[1])

    write_csv(out / "matched.csv", ["keyword", "match_tier", "records", "soilvoc_label", "soilvoc_uri", "soilvoc_type", "rule", "cleaned_keyword"], matched_rows)
    write_csv(out / "unmatched.csv", ["keyword", "records", "source_label_if_split"], unmatched_rows)
    # review sheet: top unmatched keywords that have no decision yet
    suggest = build_suggester(exact, concepts)
    sheet_rows = []
    for t, n, _src in unmatched_rows:
        if t in decisions:
            continue
        cid, clabel = suggest(t)
        sheet_rows.append([t, n, " | ".join(sorted(raw_labels[t]))[:200], cid, clabel, "", "", "", ""])
        if len(sheet_rows) >= args.top:
            break
    write_csv(sheet_path, SHEET_COLS, sheet_rows)

    # candidates to submit to SoilVoc through the GitHub issue templates
    new_by_label, synonyms = {}, []
    for d in sorted(decisions.values(), key=lambda d: d["keyword"]):
        if d["decision"] == "new_term":
            g = new_by_label.setdefault(d["new_term_label"], {"broader": d["target_concept_uri"], "kw": [], "recs": set(), "notes": set()})
            g["kw"].append(d["keyword"])
            g["recs"] |= recs.get(d["keyword"], set())
            if d["notes"]:
                g["notes"].add(d["notes"])
        elif d["decision"] in ("synonym", "broader"):
            n = len(recs.get(d["keyword"], ()))
            c = concepts[d["target_concept_uri"]]
            synonyms.append([d["target_concept_uri"], c["label"], d["keyword"], d["decision"], n, d["notes"]])
    groups = {r["label"]: r["group"] for r in read_csv(cur_dir / "new_term_groups.csv")} if (cur_dir / "new_term_groups.csv").exists() else {}
    new_terms = sorted(
        ([groups.get(lbl, ""), lbl, "", g["broader"], "", "", "", "", len(g["recs"]),
          " | ".join(k for k in g["kw"] if k != lbl), "; ".join(sorted(g["notes"]))]
         for lbl, g in new_by_label.items()),
        key=lambda r: (r[0] == "", r[0], -r[8], r[1]))
    write_csv(cur_dir / "soilvoc_new_terms.csv",
              ["group", "prefLabel", "definition", "broader", "narrower", "exactMatch", "closeMatch", "sourceLink",
               "records", "other_keywords_in_db", "notes"], new_terms)
    write_csv(cur_dir / "soilvoc_synonym_candidates.csv",
              ["concept_uri", "concept_prefLabel", "proposed_altLabel", "kind", "records", "notes"], synonyms)

    write_csv(out / "noise.csv", ["keyword", "records"], noise_rows)

    mt_rows = sorted(([t, res[t][0], len(recs[t]), *concept_cols(res[t][1])[:2], res[t][2].split(":", 1)[1], "", ""] for t in mt_kw), key=lambda r: -r[2])
    write_csv(cur_dir / "translated_review.csv",
              ["keyword", "tier", "records", "soilvoc_label", "soilvoc_uri", "language", "decision", "target_concept_uri"], mt_rows)

    used = {i for t in keywords if res[t][0] in MATCH_TIERS for i in res[t][1]}
    soilvoc_unused = [[i, c["label"], c["type"]] for i, c in concepts.items() if i not in used]
    write_csv(out / "soilvoc_not_in_db.csv", ["soilvoc_uri", "prefLabel", "type"], sorted(soilvoc_unused, key=lambda r: r[1]))

    tiers = defaultdict(lambda: [0, set()])
    for t in keywords:
        tiers[res[t][0]][0] += 1
        tiers[res[t][0]][1] |= recs[t]
    with_kw = set().union(*recs.values()) if recs else set()
    topic = [t for t in keywords if res[t][0] != "noise"]

    hit = set()
    for t in keywords:
        if res[t][0] in MATCH_TIERS:
            hit |= recs[t]
    base_tiers = ("exact", "mapped", "variant")
    hit_before = set()
    for t in keywords:
        if res[t][0] in base_tiers:
            hit_before |= recs[t]
    mt_recs = set().union(*(recs[t] for t in mt_kw)) - hit if mt_kw else set()
    n_match = sum(tiers[k][0] for k in MATCH_TIERS)
    n_before = sum(tiers[k][0] for k in base_tiers)
    n_norm = sum(tiers[k][0] for k in ("normalised", "normalised_path", "normalised_prefix"))
    n_manual = tiers["manual"][0]
    tc = defaultdict(int)
    for c in concepts.values():
        tc["procedures" if "sosa:Procedure" in c["type"] else "properties" if "sosa:ObservableProperty" in c["type"] else "general concepts"] += 1
    type_counts = ", ".join(f"{v} {k}" for k, v in tc.items())

    def pct(a, b):
        return f"{100 * a / b:.1f}%" if b else "n/a"

    lines = [
        "# Subject keywords vs SoilVoc",
        "",
        f"Database `{db_name}`, schema `{schema}` (read-only). SoilVoc concepts: {len(concepts)}.",
        "",
        "## Summary",
        "",
        "| Question | Number |",
        "|---|---|",
        f"| Unique subjects in the database (`subjects` rows) | {len({l for l, _ in rows if l})} ({len({norm(l) for l, _ in rows if l})} ignoring case and spaces) |",
        f"| Unique keywords after splitting `,` `;` | {len(keywords)} ({len(topic)} without noise) |",
        f"| SoilVoc concepts | {len(concepts)} ({type_counts}) |",
        f"| SoilVoc unique searchable labels (pref + alt) | {len(exact)} |",
        f"| Exact matches | {tiers['exact'][0]} |",
        f"| Partial matches | {tiers['mapped'][0] + tiers['variant'][0]} ({tiers['mapped'][0]} mapped through AGROVOC/GEMET/USDA, {tiers['variant'][0]} plural or UK/US spelling variants) |",
        f"| Matches after cleaning rules A1-A7 (`normalised*` tiers) | {n_norm} |",
        f"| Matches from manual decisions (`manual` tier) | {n_manual} |",
        f"| All matches | {n_match} ({pct(n_match, len(topic))} of non-noise keywords; {n_before} / {pct(n_before, len(topic))} before cleaning rules and manual decisions) |",
        f"| Suggested only: translated labels (`translated_curated` {tiers['translated_curated'][0]}, `translated_mt` {tiers['translated_mt'][0]}; not counted above) | {len(mt_kw)} keywords, {len(mt_recs)} more records |",
        f"| No match | {tiers['none'][0]} |",
        f"| Records in total | {n_records} |",
        f"| Records with subjects | {len(with_kw)} ({pct(len(with_kw), n_records)}) |",
        f"| Records with a SoilVoc subject | {len(hit)} ({pct(len(hit), n_records)} of all records, {pct(len(hit), len(with_kw))} of records with subjects; {len(hit_before)} / {pct(len(hit_before), n_records)} before cleaning rules and manual decisions) |",
        f"| SoilVoc concepts hit by at least one keyword | {len(used)} of {len(concepts)} ({pct(len(used), len(concepts))}) |",
        "",
        "Partial means a mapped or variant match, not word-inside-word matching.",
        "Noise is codes, numbers, dates, URLs, SDG/OECD labels and keywords under 3 characters.",
        "",
        "## Matches by tier",
        "",
        "| Tier | Unique keywords | % of non-noise | Records reached |",
        "|---|---|---|---|",
    ]
    for tier in (*MATCH_TIERS, *REVIEW_TIERS, "none", "noise"):
        n, rs = tiers[tier]
        base = len(topic) if tier != "noise" else len(keywords)
        lines.append(f"| {tier} | {n} | {pct(n, base)} | {len(rs)} |")
    by_dec = defaultdict(int)
    for d in decisions.values():
        by_dec[d["decision"]] += 1
    lines += [
        "",
        "## Curation",
        "",
        f"- Decisions on file: {len(decisions)} ("
        + (", ".join(f"{k} {by_dec[k]}" for k in DECISIONS if by_dec[k]) or "none yet")
        + f"); {n_imported} imported from the review sheet in this run",
        f"- `curation/review_sheet.csv`: {len(sheet_rows)} undecided keywords to review (top {args.top} by records)",
        f"- `curation/soilvoc_new_terms.csv`: {len(new_terms)} proposed new terms",
        f"- `curation/soilvoc_synonym_candidates.csv`: {len(synonyms)} proposed synonyms / broader links",
    ]
    lines += [
        "",
        "## Top matched keywords",
        "",
        "| Keyword | Tier | Records | SoilVoc concept |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in matched_rows[:20]]
    lines += ["", "## Top unmatched keywords", "", "| Keyword | Records |", "|---|---|"]
    lines += [f"| {r[0]} | {r[1]} |" for r in unmatched_rows[:30]]
    lines += [
        "",
        "## Files",
        "",
        "- `matched.csv`: keyword, tier, records, SoilVoc concept",
        "- `unmatched.csv`: keywords with no SoilVoc match, by record count",
        "- `noise.csv`: codes, numbers, dates, URLs and SDG/OECD labels left out of the percentages",
        "- `soilvoc_not_in_db.csv`: SoilVoc concepts that no keyword matched",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:22]))
    print(f"\nFiles written to {out}")


if __name__ == "__main__":
    main()
