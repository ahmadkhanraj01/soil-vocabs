"""Propose SoilVoc concepts for records from title + abstract, with a local or hosted LLM.

Steps per record
  1. embed the text and every SoilVoc label (Ollama embedding model) and take the TOP_K closest labels
  2. ask an LLM to choose from that list only (JSON answer)
  3. keep only choices that are in the list; anything else is counted as invalid

Safe by design: the database is only read (SELECT, read-only session) and never written.
The run is resumable: results are appended to results.jsonl, and a run that is stopped or crashes
continues where it stopped. Progress is written to progress.json (see scripts/progress_ui.py).

Examples
  python scripts/llm_extract_subjects.py --records sample.json --limit 50
  python scripts/llm_extract_subjects.py --from-db --model qwen2.5:14b --workers 2
  python scripts/llm_extract_subjects.py --from-db --provider openrouter --model <id> --workers 4

Input files: {"records": [...]}, a JSON list, or a CSV, with identifier, title, abstract.
Full instructions: LLM_EXTRACTION.md
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import signal
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
SCHEMA = {"type": "object", "properties": {"terms": {"type": "array", "items": {"type": "string"}}}, "required": ["terms"]}
RECENT = 25


class FatalError(Exception):
    """Stops the whole run (bad key, daily quota used up, Ollama not running)."""


def load_compare():
    spec = importlib.util.spec_from_file_location("cmp", ROOT / "scripts" / "compare_subjects_to_soilvoc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def post(path, body, timeout=600):
    req = urllib.request.Request(OLLAMA + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.URLError as e:
        raise FatalError(f"Cannot reach Ollama at {OLLAMA} ({e.reason}). Is `ollama serve` running?")


def embed(texts, prefix, model):
    out = []
    for i in range(0, len(texts), 64):
        out += post("/api/embed", {"model": model, "input": [prefix + t for t in texts[i:i + 64]]})["embeddings"]
    m = np.array(out, dtype=np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def openrouter_key():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise FatalError("OPENROUTER_API_KEY is not set (environment or .env)")
    return key


def ask(provider, model, prompt):
    """Returns the model's JSON text. 'ollama' stays on this machine; 'openrouter' sends the prompt to the API."""
    if provider == "ollama":
        r = post("/api/generate", {"model": model, "prompt": prompt, "stream": False, "format": SCHEMA,
                                   "options": {"temperature": 0, "num_predict": 300}})
        return r["response"]
    body = {"model": model, "temperature": 0, "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "terms", "strict": True, "schema": SCHEMA}}}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + openrouter_key()})
    for wait in (0, 5, 20, 60):
        time.sleep(wait)
        try:
            return json.load(urllib.request.urlopen(req, timeout=180))["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            if e.code in (401, 402, 403) or "free-models-per-day" in detail:
                raise FatalError(f"OpenRouter HTTP {e.code}: {detail}")
            if e.code not in (429, 500, 502, 503):
                raise RuntimeError(f"OpenRouter HTTP {e.code}")
    raise RuntimeError("OpenRouter kept failing for this record")


# ---------------------------------------------------------------- input
def read_records_file(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with open(p, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    data = json.load(open(p, encoding="utf-8"))
    return data["records"] if isinstance(data, dict) else data


def read_records_db(cmp, limit, seed):
    """Records without any subject that have title + abstract. Read-only SELECT."""
    import psycopg2

    env = cmp.load_env(str(ROOT / ".env"))
    sfx = "1" if "DB_HOST1" in env else ""
    g = lambda k: env[k + sfx]
    schema = env.get("DB_SCHEMA" + sfx, "public")
    if not re.fullmatch(r"\w+", schema):
        raise SystemExit("bad schema name")
    conn = psycopg2.connect(host=g("DB_HOST"), port=g("DB_PORT"), dbname=g("DB_NAME"),
                            user=g("DB_USER"), password=g("DB_PASSWORD"), connect_timeout=10)
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cur.execute(f"select setseed(%s)", (seed,))
    cur.execute(
        f"select r.identifier, r.title, r.abstract from {schema}.records r "
        f"where not exists (select 1 from {schema}.record_subject rs where rs.record_id = r.id) "
        f"and r.abstract is not null and length(r.abstract) > 30 order by random()"
        + (f" limit {int(limit)}" if limit else "")
    )
    rows = [{"identifier": a, "title": b, "abstract": c} for a, b, c in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------- progress
class Progress:
    def __init__(self, out, cfg, total, done_before, results_path, prior=None):
        self.out, self.cfg, self.total = Path(out), cfg, total
        self.done_before = done_before
        self.started = time.time()
        self.lock = threading.Lock()
        self.s = {"done": done_before, "chosen": 0, "empty": 0, "invalid": 0, "errors": 0}
        self.recent, self.hist = [], {}
        for r in prior or []:  # statistics of the records finished in an earlier session
            self.s["chosen"] += len(r["terms"])
            self.s["empty"] += not r["terms"]
            self.s["invalid"] += r.get("invalid", 0)
            k = str(min(len(r["terms"]), 10))
            self.hist[k] = self.hist.get(k, 0) + 1
        self.session_done = 0
        self.status = "starting"
        self.message = ""
        self.results_path = results_path
        self.write()

    def add(self, rec, chosen, invalid, secs):
        with self.lock:
            self.s["done"] += 1
            self.session_done += 1
            self.s["chosen"] += len(chosen)
            self.s["empty"] += not chosen
            self.s["invalid"] += invalid
            n = str(min(len(chosen), 10))
            self.hist[n] = self.hist.get(n, 0) + 1
            self.recent.append({"id": rec["identifier"], "title": (rec.get("title") or "")[:110], "terms": chosen,
                                "seconds": round(secs, 1)})
            self.recent = self.recent[-RECENT:]
            self.write()

    def error(self, rec, msg):
        with self.lock:
            self.s["errors"] += 1
            self.recent.append({"id": rec["identifier"], "title": (rec.get("title") or "")[:110], "terms": [],
                                "error": msg[:160], "seconds": 0})
            self.recent = self.recent[-RECENT:]
            self.write()

    def set(self, status, message=""):
        with self.lock:
            self.status, self.message = status, message
            self.write()

    def write(self):
        elapsed = time.time() - self.started
        rate = self.session_done / elapsed * 60 if elapsed > 5 and self.session_done else 0
        left = self.total - self.s["done"]
        d = {**self.cfg, **self.s, "total": self.total, "remaining": left, "status": self.status,
             "message": self.message, "started_at": self.cfg["started_at"], "updated_at": now(),
             "elapsed_seconds": round(elapsed), "records_per_minute": round(rate, 1),
             "eta_seconds": round(left / rate * 60) if rate else None,
             "avg_terms": round(self.s["chosen"] / max(1, self.s["done"]), 2),
             "terms_histogram": self.hist, "recent": self.recent}
        tmp = self.out / "progress.json.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.out / "progress.json")


def export_csv(out, concepts):
    rows = []
    with open(out / "results.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            for t in r["terms"]:
                rows.append([r["id"], t["label"], t["uri"], concepts[t["uri"]]["label"], r["model"]])
    with open(out / "llm_concepts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["record_identifier", "matched_label", "concept_uri", "concept_label", "model"])
        w.writerows(rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--records", help="JSON or CSV file with identifier, title, abstract")
    src.add_argument("--from-db", action="store_true", help="records without subjects from the database in .env (read-only)")
    ap.add_argument("--limit", type=int, default=0, help="max records (0 = all)")
    ap.add_argument("--seed", type=float, default=0.42, help="random order for --from-db, -1..1")
    ap.add_argument("--provider", choices=("ollama", "openrouter"), default="ollama")
    ap.add_argument("--model", default="llama3.2:3b", help="Ollama tag, or an OpenRouter model id")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--top-k", type=int, default=25, help="candidate labels shown to the LLM per record")
    ap.add_argument("--max-terms", type=int, default=5)
    ap.add_argument("--workers", type=int, default=1, help="records processed in parallel")
    ap.add_argument("--out", default=str(ROOT / "reports" / "llm_extraction"))
    ap.add_argument("--fresh", action="store_true", help="ignore earlier results in --out and start over")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.jsonl"
    if args.fresh and results_path.exists():
        results_path.unlink()

    cmp = load_compare()
    concepts, exact = cmp.load_soilvoc()
    # procedures are measurement identifiers (e.g. ExchAcid_ph0-kcl1m), never found in running text
    ids = {i for i, c in concepts.items() if "sosa:Procedure" not in c["type"]}
    labels = sorted((l, i) for l, s in exact.items() for i in s if i in ids and len(l) >= 3)
    names = [l for l, _ in labels]
    label_ids = [i for _, i in labels]

    cfg = {"provider": args.provider, "model": args.model, "embed_model": args.embed_model, "workers": args.workers,
           "top_k": args.top_k, "source": "database" if args.from_db else args.records, "out": str(out),
           "started_at": now()}
    prog = Progress(out, cfg, 0, 0, results_path)
    prog.set("loading", "reading records")

    recs = read_records_db(cmp, args.limit, args.seed) if args.from_db else read_records_file(args.records)
    if args.limit:
        recs = recs[: args.limit]
    wanted = {r.get("identifier") for r in recs}
    prior, done_ids = [], set()
    if results_path.exists():
        with open(results_path, encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    if r["id"] in wanted and r["id"] not in done_ids:
                        done_ids.add(r["id"])
                        prior.append(r)
    todo = [r for r in recs if r.get("identifier") not in done_ids]
    print(f"{len(recs)} records, {len(done_ids)} already done, {len(todo)} to do")
    prog = Progress(out, cfg, len(recs), len(done_ids), results_path, prior)

    # label embeddings are cached per model + label set
    key = hashlib.sha1((args.embed_model + "\n".join(names)).encode()).hexdigest()[:12]
    cache = out / f"label_embeddings_{key}.npy"
    prog.set("loading", "embedding SoilVoc labels (once)")
    try:
        if cache.exists():
            lab_emb = np.load(cache)
        else:
            lab_emb = embed(names, "search_document: ", args.embed_model)
            np.save(cache, lab_emb)
    except FatalError as e:
        prog.set("error", str(e))
        raise SystemExit(str(e))

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    write_lock = threading.Lock()
    consecutive_errors = [0]
    fatal = []

    def work(r):
        if stop.is_set() or fatal:
            return
        text = f"{r.get('title') or ''}. {r.get('abstract') or ''}".strip(" .")
        text = re.sub(r"<[^>]+>", " ", text)[:1500]
        t0 = time.time()
        try:
            q = embed([text], "search_query: ", args.embed_model)[0]
            order = np.argsort(-(lab_emb @ q))
            short, seen = {}, set()
            for j in order:
                if label_ids[j] not in seen:
                    seen.add(label_ids[j])
                    short[names[j]] = label_ids[j]
                if len(short) >= args.top_k:
                    break
            prompt = (
                "Document:\n" + text + "\n\nCandidate soil terms:\n" + "\n".join("- " + n for n in short)
                + f"\n\nChoose at most {args.max_terms} candidate terms that the document is clearly about. "
                "Leave out terms that are only loosely related. Use only terms from the list, written exactly "
                'as listed. If none fit, answer with an empty list. Answer as JSON: {"terms": [...]}.'
            )
            raw = ask(args.provider, args.model, prompt)
            try:
                parsed = json.loads(raw)["terms"]
            except (json.JSONDecodeError, KeyError, TypeError):
                raise RuntimeError("model did not return the JSON format")
            chosen, invalid = [], 0
            lowered = {n.lower(): n for n in short}
            for x in parsed if isinstance(parsed, list) else []:
                n = lowered.get(str(x).strip().lower())
                if n and n not in [c["label"] for c in chosen]:
                    chosen.append({"label": n, "uri": short[n]})
                elif not n:
                    invalid += 1
            chosen = chosen[: args.max_terms]
        except FatalError as e:
            fatal.append(str(e))
            return
        except Exception as e:  # one bad record must not stop the run; it is retried on the next start
            with write_lock:
                consecutive_errors[0] += 1
                if consecutive_errors[0] >= 8:
                    fatal.append(f"8 errors in a row, last: {e}")
            prog.error(r, str(e))
            return
        consecutive_errors[0] = 0
        with write_lock:
            with open(results_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": r["identifier"], "title": (r.get("title") or "")[:200], "terms": chosen,
                                    "invalid": invalid, "model": args.model, "at": now()}, ensure_ascii=False) + "\n")
        prog.add(r, [c["label"] for c in chosen], invalid, time.time() - t0)

    prog.set("running")
    print("running; Ctrl+C stops safely and the next start continues")
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            list(ex.map(work, todo))
    finally:
        n = export_csv(out, concepts) if results_path.exists() else 0
        if fatal:
            prog.set("error", fatal[0])
            print("STOPPED:", fatal[0])
        elif stop.is_set():
            prog.set("stopped", "stopped by user; run the same command to continue")
        else:
            prog.set("finished")
        print(f"{prog.s['done']}/{prog.total} records done, {n} record-concept rows in {out / 'llm_concepts.csv'}")


if __name__ == "__main__":
    main()
