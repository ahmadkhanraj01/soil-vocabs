"""Load the approved dry run into the DB (Option 1, Step 5).

Usage: python scripts/load_soilvoc_links.py [--db 1] [--links ...] [--noise ...]

Steps, in ONE transaction (rolled back on any error):
  1. backup subjects (id, label, vocabulary_name) to
     validate.subjects_pre_soilvoc_backup_<ts>
  2. delete this script's previous links (subject_soilvoc is script-owned) and
     insert every row of dry_run_links.csv
  3. subjects.vocabulary_name = 'SoilVoc' for linked subjects, 'noise' for the
     noise list, untouched otherwise (never touches subjects.label / .uri)

Subject resolution: exact subject_id first; if the id is not in the target DB
(dev and stage have disjoint ids), fall back to the label (unique per label in
both DBs). Unresolvable subjects are reported, not silently dropped.

Requires soilvoc_types to be loaded (scripts/load_soilvoc_types.py) first.
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import dotenv_values
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parent.parent
LINK_TYPES = ("exact", "synonym", "translation", "mapped", "variant", "broader", "inside")


def connect(env, sfx):
    for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        if key + sfx not in env:
            sys.exit(f"missing {key}{sfx} in .env")
    return psycopg2.connect(host=env["DB_HOST" + sfx], port=env["DB_PORT" + sfx],
                            dbname=env["DB_NAME" + sfx], user=env["DB_USER" + sfx],
                            password=env["DB_PASSWORD" + sfx], connect_timeout=15)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", choices=("1",), default="1", help="1=stage (msp-kh-stage, schema validate). Dev is never written.")
    ap.add_argument("--links", default=str(ROOT / "reports/soilvoc_levels_vs_db/dry_run_links.csv"))
    ap.add_argument("--noise", default=str(ROOT / "reports/soilvoc_levels_vs_db/noise_subjects.csv"))
    args = ap.parse_args()

    with open(args.links, newline="") as f:
        links = list(csv.DictReader(f))
    with open(args.noise, newline="") as f:
        noise = list(csv.DictReader(f))

    bad = [l for l in links if l["link_type"] not in LINK_TYPES]
    if bad:
        sys.exit(f"{len(bad)} rows with unknown link_type, e.g. {bad[0]['link_type']!r}")

    env = dotenv_values(ROOT / ".env")
    conn = connect(env, args.db)
    conn.autocommit = False
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {}

    try:
        with conn.cursor() as cur:
            # ---- resolve subjects (id, then label) --------------------------
            cur.execute("SELECT id, label FROM validate.subjects")
            by_id, by_label = {}, {}
            for sid, label in cur.fetchall():
                by_id[str(sid)] = label
                if label not in by_label:      # first wins; labels are unique
                    by_label[label] = sid

            def resolve(sid, label):
                """target subject id, or None (id match, else label match)."""
                if sid in by_id:
                    return sid
                target = by_label.get(label)
                return str(target) if target is not None else None

            resolved, unresolved = {}, Counter()
            for l in links:
                label = l["original_label"]
                target = resolve(l["subject_id"], label)
                if target:
                    resolved[l["subject_id"]] = target
                else:
                    unresolved[label] += 1
            resolved_noise = {}
            for n in noise:
                target = resolve(n["subject_id"], n["label"])
                if target:
                    resolved_noise[n["subject_id"]] = target
                else:
                    unresolved[n["label"]] += 1

            # ---- soilvoc_types present? -------------------------------------
            cur.execute("SELECT COUNT(*) FROM validate.soilvoc_types")
            n_types = cur.fetchone()[0]
            if n_types == 0:
                raise RuntimeError("soilvoc_types is empty — run load_soilvoc_types.py first")
            cur.execute("SELECT code FROM validate.soilvoc_types")
            codes = {r[0] for r in cur.fetchall()}
            missing_codes = {l["soilvoc_uri"] for l in links} - codes
            if missing_codes:
                raise RuntimeError(
                    f"{len(missing_codes)} concepts not in soilvoc_types, "
                    f"e.g. {sorted(missing_codes)[:3]} — run load_soilvoc_types.py")

            # ---- 1. backup --------------------------------------------------
            btable = f"validate.subjects_pre_soilvoc_backup_{ts}"
            cur.execute(f"""CREATE TABLE {btable} AS
                            SELECT id, label, vocabulary_name FROM validate.subjects""")

            # ---- 2. links ---------------------------------------------------
            cur.execute("DELETE FROM validate.subject_soilvoc")
            to_insert, no_link = [], []
            for l in links:
                sid = resolved.get(l["subject_id"])
                if sid is None:
                    no_link.append(l)
                    continue
                to_insert.append((sid, l["soilvoc_uri"], l["link_type"],
                                  l["part"] or None,
                                  l["reviewed"].strip().lower() == "true"))
            execute_values(cur, """
                INSERT INTO validate.subject_soilvoc
                    (subject_id, soilvoc_code, link_type, part, reviewed)
                VALUES %s
                ON CONFLICT (subject_id, soilvoc_code) DO UPDATE
                    SET link_type = EXCLUDED.link_type, part = EXCLUDED.part,
                        reviewed = EXCLUDED.reviewed""",
                to_insert, page_size=500)

            # ---- 3. vocabulary_name -----------------------------------------
            linked_ids = set(resolved.values())          # any linked subject
            noise_ids = {resolved_noise[sid] for sid in resolved_noise} - linked_ids
            # clear this pipeline's previous marks, then apply the current set
            cur.execute("""
                UPDATE validate.subjects SET vocabulary_name = NULL
                WHERE vocabulary_name IN ('SoilVoc', 'noise')""")
            if linked_ids:
                cur.execute("UPDATE validate.subjects SET vocabulary_name = 'SoilVoc' "
                            "WHERE id = ANY(%s::uuid[])", (list(linked_ids),))
            if noise_ids:
                cur.execute("UPDATE validate.subjects SET vocabulary_name = 'noise' "
                            "WHERE id = ANY(%s::uuid[])", (list(noise_ids),))

            # ---- verify ------------------------------------------------------
            cur.execute("""SELECT COUNT(*), COUNT(DISTINCT soilvoc_code),
                                  COUNT(DISTINCT subject_id)
                           FROM validate.subject_soilvoc""")
            report["links"], report["concepts"], report["linked_subjects"] = cur.fetchone()
            cur.execute("""SELECT COUNT(DISTINCT rs.record_id)
                           FROM validate.record_subject rs
                           JOIN validate.subject_soilvoc ss ON ss.subject_id = rs.subject_id""")
            report["records"] = cur.fetchone()[0]
            cur.execute("""SELECT COUNT(DISTINCT rs.record_id)
                           FROM validate.record_subject rs
                           JOIN validate.subject_soilvoc ss ON ss.subject_id = rs.subject_id
                           WHERE ss.link_type <> 'inside'""")
            report["records_direct"] = cur.fetchone()[0]
            cur.execute("""SELECT vocabulary_name, COUNT(*) FROM validate.subjects
                           WHERE vocabulary_name IS NOT NULL GROUP BY 1 ORDER BY 1""")
            report["vocab"] = dict(cur.fetchall())
            cur.execute("SELECT COUNT(*) FROM validate.record_subject rs "
                        "JOIN validate.subjects s "
                        "ON s.id = rs.subject_id WHERE s.vocabulary_name = 'noise'")
            report["noise_uses"] = cur.fetchone()[0]
            report["backup"] = btable
            report["unresolved_links"] = len(no_link)
            report["unresolved_noise"] = len(noise) - len(resolved_noise)
            report["unresolved_samples"] = [l["original_label"] for l in no_link[:5]]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"LOADED into {env['DB_NAME' + args.db]}.validate (db {args.db})")
    print(f"  subject_soilvoc    : {report['links']} links, "
          f"{report['concepts']} concepts, {report['linked_subjects']} subjects")
    print(f"  records with link  : {report['records']} "
          f"(direct, excl. inside: {report['records_direct']})")
    print(f"  vocabulary_name    : {report['vocab']} "
          f"(noise used {report['noise_uses']} times)")
    print(f"  backup             : {report['backup']}")
    if report["unresolved_links"] or report["unresolved_noise"]:
        print(f"  NOT resolved (subject absent in this DB): "
              f"{report['unresolved_links']} links, {report['unresolved_noise']} noise "
              f"subjects; e.g. {report['unresolved_samples']}")


if __name__ == "__main__":
    main()
