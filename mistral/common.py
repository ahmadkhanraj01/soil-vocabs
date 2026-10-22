"""Shared code for the Mistral extraction (mistral/extract.py, mistral/estimate.py, mistral/ui.py).

Same idea as scripts/llm_extract_subjects.py (local Ollama), but the choosing is done by the Mistral API
and every call is measured: tokens, seconds and cost. The database is only read, never written.
"""
import hashlib
import importlib.util
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
API = "https://api.mistral.ai/v1"
SCHEMA = {"type": "object", "properties": {"terms": {"type": "array", "items": {"type": "string"}}}, "required": ["terms"]}
RECENT = 25


class FatalError(Exception):
    """Stops the run: bad key, no credit, rate limit that does not go away."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def api_key():
    key = os.environ.get("MISTRAL_API_KEY", "")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("MISTRAL_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise FatalError("MISTRAL_API_KEY is not set (environment or .env)")
    return key


def prices():
    return json.loads((HERE / "prices.json").read_text(encoding="utf-8"))


def call(path, body, stats=None):
    """POST to the Mistral API. Retries 429/5xx (honours Retry-After). Returns (json, seconds)."""
    req = urllib.request.Request(API + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + api_key()})
    last = ""
    for attempt, wait in enumerate((0, 2, 5, 15, 40, 90)):
        time.sleep(wait)
        t0 = time.time()
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            return r, time.time() - t0
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            if e.code in (401, 402, 403):
                raise FatalError(f"Mistral HTTP {e.code}: {detail}")
            last = f"HTTP {e.code} {detail[:120]}"
            if e.code == 429 and stats is not None:
                stats["rate_limited"] = stats.get("rate_limited", 0) + 1
            ra = e.headers.get("Retry-After")
            if ra and ra.isdigit():
                time.sleep(min(int(ra), 90))
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(last)
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
    raise RuntimeError("Mistral kept failing: " + last)


def embed(texts, model, stats=None):
    """Returns (normalised matrix, tokens used)."""
    out, tokens = [], 0
    for i in range(0, len(texts), 64):
        r, _ = call("/embeddings", {"model": model, "input": texts[i:i + 64]}, stats)
        out += [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
        tokens += r["usage"]["prompt_tokens"]
    m = np.array(out, dtype=np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9), tokens


class Context:
    """Vocabulary, label embeddings and settings shared by all workers."""

    def __init__(self, model, embed_model, out, top_k=25, max_terms=5):
        self.model, self.embed_model, self.top_k, self.max_terms = model, embed_model, top_k, max_terms
        p = prices()
        self.price = p["models"].get(model)
        if not self.price:
            raise SystemExit(f"{model} is not in mistral/prices.json; add its prices there first")
        self.embed_price = p["embeddings"].get(embed_model, {"input": 0})["input"]
        self.cmp = load_module("cmp", ROOT / "scripts" / "compare_subjects_to_soilvoc.py")
        self.local = load_module("loc", ROOT / "scripts" / "llm_extract_subjects.py")
        self.concepts, exact = self.cmp.load_soilvoc()
        ids = {i for i, c in self.concepts.items() if "sosa:Procedure" not in c["type"]}
        labels = sorted((l, i) for l, s in exact.items() for i in s if i in ids and len(l) >= 3)
        self.names = [l for l, _ in labels]
        self.label_ids = [i for _, i in labels]
        key = hashlib.sha1((embed_model + "\n".join(self.names)).encode()).hexdigest()[:12]
        cache = Path(out) / f"label_embeddings_{key}.npy"
        self.label_embed_tokens = 0
        if cache.exists():
            self.lab_emb = np.load(cache)
        else:
            self.lab_emb, self.label_embed_tokens = embed(self.names, embed_model)
            np.save(cache, self.lab_emb)

    def cost(self, tin, tout, tembed):
        return (tin * self.price["input"] + tout * self.price["output"] + tembed * self.embed_price) / 1e6

    def records_from_db(self, seed):
        return self.local.read_records_db(self.cmp, 0, seed)

    def process(self, rec, stats):
        text = f"{rec.get('title') or ''}. {rec.get('abstract') or ''}".strip(" .")
        text = re.sub(r"<[^>]+>", " ", text)[:1500]
        q, t_embed = embed([text], self.embed_model, stats)
        order = np.argsort(-(self.lab_emb @ q[0]))
        short, seen = {}, set()
        for j in order:
            if self.label_ids[j] not in seen:
                seen.add(self.label_ids[j])
                short[self.names[j]] = self.label_ids[j]
            if len(short) >= self.top_k:
                break
        prompt = (
            "Document:\n" + text + "\n\nCandidate soil terms:\n" + "\n".join("- " + n for n in short)
            + f"\n\nChoose at most {self.max_terms} candidate terms that the document is clearly about. "
            "Leave out terms that are only loosely related. Use only terms from the list, written exactly "
            'as listed. If none fit, answer with an empty list. Answer as JSON: {"terms": [...]}.'
        )
        r, secs = call("/chat/completions", {
            "model": self.model, "temperature": 0, "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "terms", "schema": SCHEMA, "strict": True}},
        }, stats)
        try:
            parsed = json.loads(r["choices"][0]["message"]["content"])["terms"]
        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            raise RuntimeError("model did not return the JSON format")
        lowered = {n.lower(): n for n in short}
        chosen, invalid = [], 0
        for x in parsed if isinstance(parsed, list) else []:
            n = lowered.get(str(x).strip().lower())
            if n and n not in [c["label"] for c in chosen]:
                chosen.append({"label": n, "uri": short[n]})
            elif not n:
                invalid += 1
        u = r["usage"]
        return {"id": rec["identifier"], "title": (rec.get("title") or "")[:200], "terms": chosen[: self.max_terms],
                "invalid": invalid, "model": self.model, "tokens_in": u["prompt_tokens"], "tokens_out": u["completion_tokens"],
                "tokens_embed": t_embed, "api_seconds": round(secs, 2),
                "cost_usd": round(self.cost(u["prompt_tokens"], u["completion_tokens"], t_embed), 8), "at": now()}


class Progress:
    """Writes progress.json for mistral/ui.py after every record."""

    def __init__(self, out, cfg, total, target_total, prior):
        self.out, self.cfg, self.total, self.target = Path(out), cfg, total, target_total
        self.lock = threading.Lock()
        self.started = time.time()
        self.status, self.message = "starting", ""
        self.s = {"done": 0, "chosen": 0, "empty": 0, "invalid": 0, "errors": 0,
                  "tokens_in": 0, "tokens_out": 0, "tokens_embed": 0, "cost_usd": 0.0}
        self.stats = {}
        self.hist, self.recent, self.session_done = {}, [], 0
        for r in prior:
            self._count(r)
        self.write()

    def _count(self, r):
        s = self.s
        s["done"] += 1
        s["chosen"] += len(r["terms"])
        s["empty"] += not r["terms"]
        s["invalid"] += r.get("invalid", 0)
        for k in ("tokens_in", "tokens_out", "tokens_embed", "cost_usd"):
            s[k] += r.get(k, 0)
        k = str(min(len(r["terms"]), 10))
        self.hist[k] = self.hist.get(k, 0) + 1

    def add(self, r):
        with self.lock:
            self._count(r)
            self.session_done += 1
            self.recent = (self.recent + [{"id": r["id"], "title": r["title"][:110],
                                           "terms": [t["label"] for t in r["terms"]], "seconds": r["api_seconds"],
                                           "cost_usd": r["cost_usd"]}])[-RECENT:]
            self.write()

    def error(self, rec, msg):
        with self.lock:
            self.s["errors"] += 1
            self.recent = (self.recent + [{"id": rec["identifier"], "title": (rec.get("title") or "")[:110],
                                           "terms": [], "error": msg[:160], "seconds": 0, "cost_usd": 0}])[-RECENT:]
            self.write()

    def set(self, status, message=""):
        with self.lock:
            self.status, self.message = status, message
            self.write()

    def write(self):
        el = time.time() - self.started
        s = self.s
        rate = self.session_done / el * 60 if el > 5 and self.session_done else 0
        left = self.total - s["done"]
        per = s["cost_usd"] / s["done"] if s["done"] else 0
        d = {**self.cfg, **s, "total": self.total, "target_total": self.target, "remaining": left,
             "status": self.status, "message": self.message, "updated_at": now(), "elapsed_seconds": round(el),
             "records_per_minute": round(rate, 1), "eta_seconds": round(left / rate * 60) if rate else None,
             "avg_terms": round(s["chosen"] / max(1, s["done"]), 2), "cost_usd": round(s["cost_usd"], 6),
             "cost_per_record_usd": round(per, 6), "projected_cost_usd": round(per * self.target, 2) if per else None,
             "projected_seconds": round(self.target / rate * 60) if rate else None,
             "rate_limited": self.stats.get("rate_limited", 0), "terms_histogram": self.hist, "recent": self.recent}
        tmp = self.out / "progress.json.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.out / "progress.json")


def run_batch(ctx, records, out, workers, cfg, target_total, stop):
    """Process records (skipping finished ones in out/results.jsonl). Appends results, updates progress."""
    from concurrent.futures import ThreadPoolExecutor

    out = Path(out)
    results = out / "results.jsonl"
    wanted = {r["identifier"] for r in records}
    prior, done = [], set()
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["id"] in wanted and r["id"] not in done:
                    done.add(r["id"])
                    prior.append(r)
    todo = [r for r in records if r["identifier"] not in done]
    prog = Progress(out, cfg, len(records), target_total, prior)
    prog.s["label_embed_tokens"] = ctx.label_embed_tokens
    t_start = time.time()
    lock, fatal, errs = threading.Lock(), [], [0]

    def work(rec):
        if stop.is_set() or fatal:
            return
        try:
            r = ctx.process(rec, prog.stats)
            r["t"] = round(time.time() - t_start, 2)
        except FatalError as e:
            fatal.append(str(e))
            return
        except Exception as e:
            with lock:
                errs[0] += 1
                if errs[0] >= 8:
                    fatal.append(f"8 errors in a row, last: {e}")
            prog.error(rec, str(e))
            return
        errs[0] = 0
        with lock:
            with open(results, "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        prog.add(r)

    prog.set("running")
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(work, todo))
    finally:
        if fatal:
            prog.set("error", fatal[0])
        elif stop.is_set():
            prog.set("stopped", "stopped by user; run the same command to continue")
        else:
            prog.set("finished")
    return prog, fatal
