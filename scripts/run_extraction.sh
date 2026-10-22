#!/usr/bin/env bash
# One command for the LLM subject extraction: sets up, downloads the models, opens the progress
# page and processes the records that have no subjects. Read-only on the database.
#
#   bash scripts/run_extraction.sh                       # all records without subjects
#   LIMIT=200 bash scripts/run_extraction.sh             # first test: 200 random records
#   MODEL=qwen2.5:14b WORKERS=2 bash scripts/run_extraction.sh
#
# Settings (environment variables, all optional)
#   MODEL=llama3.2:3b     Ollama model that chooses the concepts
#   EMBED_MODEL=nomic-embed-text
#   WORKERS=1             records processed at the same time (also start Ollama with OLLAMA_NUM_PARALLEL=N)
#   LIMIT=0               number of records, 0 = all
#   OUT=reports/llm_extraction
#   PORT=8765             progress page
#   YES=1                 do not ask for confirmation
#   NO_BROWSER=1          do not open the browser
#   KEEP_UI=0             stop the progress page when the run ends (default: keep it until Ctrl+C)
# Stop with Ctrl+C. Running the same command again continues where it stopped.
set -euo pipefail

cd "$(dirname "$0")/.."
MODEL="${MODEL:-llama3.2:3b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
WORKERS="${WORKERS:-1}"
LIMIT="${LIMIT:-0}"
OUT="${OUT:-reports/llm_extraction}"
PORT="${PORT:-8765}"
KEEP_UI="${KEEP_UI:-1}"

say() { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. $2"; exit 1; }; }

say "Checking tools"
need python3 "Install Python 3.10 or newer."
need ollama "Install Ollama from https://ollama.com and run this script again."
[ -f .env ] || { echo "Missing .env with the database settings (DB_HOST1, DB_PORT1, DB_NAME1, DB_USER1, DB_PASSWORD1, DB_SCHEMA1)."; exit 1; }

say "Python packages"
if ! python3 -c "import numpy, psycopg2" 2>/dev/null; then
  python3 -m pip install -r requirements-llm.txt
fi

say "Ollama server"
if ! curl -s -m 3 http://localhost:11434/api/tags >/dev/null; then
  echo "starting ollama serve in the background"
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  for _ in $(seq 1 30); do curl -s -m 2 http://localhost:11434/api/tags >/dev/null && break; sleep 1; done
fi
curl -s -m 3 http://localhost:11434/api/tags >/dev/null || { echo "Ollama does not answer. See /tmp/ollama-serve.log"; exit 1; }

say "Downloading models (skipped when already present)"
ollama pull "$EMBED_MODEL"
ollama pull "$MODEL"

COUNT=$(python3 - <<'PY'
import importlib.util, re
from pathlib import Path
import psycopg2
spec = importlib.util.spec_from_file_location("c", "scripts/compare_subjects_to_soilvoc.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
env = c.load_env(".env"); s = "1" if "DB_HOST1" in env else ""; g = lambda k: env[k + s]
schema = env.get("DB_SCHEMA" + s, "public")
assert re.fullmatch(r"\w+", schema)
conn = psycopg2.connect(host=g("DB_HOST"), port=g("DB_PORT"), dbname=g("DB_NAME"), user=g("DB_USER"), password=g("DB_PASSWORD"), connect_timeout=10)
conn.set_session(readonly=True); cur = conn.cursor()
cur.execute(f"select count(*) from {schema}.records r where not exists (select 1 from {schema}.record_subject rs where rs.record_id = r.id) and r.abstract is not null and length(r.abstract) > 30")
print(cur.fetchone()[0])
PY
)
N="$COUNT"; [ "$LIMIT" -gt 0 ] && [ "$LIMIT" -lt "$COUNT" ] && N="$LIMIT"
say "Plan"
echo "records without subjects (with a title and abstract): $COUNT"
echo "to process now: $N   model: $MODEL   workers: $WORKERS   output: $OUT"
echo "the database is only read; nothing is written to it"
if [ "${YES:-0}" != "1" ]; then
  read -r -p "Start? [y/N] " a
  [ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "cancelled"; exit 0; }
fi

mkdir -p "$OUT"
say "Progress page: http://localhost:$PORT"
python3 scripts/progress_ui.py --out "$OUT" --port "$PORT" >/tmp/progress_ui.log 2>&1 &
UI_PID=$!
cleanup() { kill "$UI_PID" 2>/dev/null || true; }
trap cleanup EXIT
sleep 1
if [ "${NO_BROWSER:-0}" != "1" ]; then
  (xdg-open "http://localhost:$PORT" || open "http://localhost:$PORT") >/dev/null 2>&1 || echo "open http://localhost:$PORT in your browser"
fi

say "Extracting (Ctrl+C stops safely; run the same command to continue)"
ARGS=(--from-db --model "$MODEL" --embed-model "$EMBED_MODEL" --workers "$WORKERS" --out "$OUT")
[ "$LIMIT" -gt 0 ] && ARGS+=(--limit "$LIMIT")
python3 -u scripts/llm_extract_subjects.py "${ARGS[@]}"

say "Done. Results: $OUT/llm_concepts.csv"
if [ "$KEEP_UI" = "1" ]; then
  echo "The progress page stays open at http://localhost:$PORT. Press Ctrl+C to close it."
  wait "$UI_PID"
fi
