"""Local progress dashboard for scripts/llm_extract_subjects.py.

Read-only: it only reads progress.json and results.jsonl from the output folder.
No database access, no internet, standard library only.

  python scripts/progress_ui.py                       # watches reports/llm_extraction
  python scripts/progress_ui.py --out reports/run2 --port 8765

Then open http://localhost:8765 . Start the extraction in another terminal.
"""
import argparse
import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SoilVoc extraction progress</title>
<style>
:root{--bg:#f6f7f4;--card:#fff;--ink:#1d2a1f;--mute:#667064;--line:#dfe3da;--accent:#2f6b3a;--warn:#b26a00;--bad:#b3261e;--ok:#2f6b3a}
@media (prefers-color-scheme:dark){:root{--bg:#141a15;--card:#1c241d;--ink:#e6ece6;--mute:#93a08f;--line:#2c382d;--accent:#6fbf7d;--warn:#e0a040;--bad:#f0807a;--ok:#6fbf7d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mute);font-size:13px;margin-bottom:16px;word-break:break-all}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.running{color:var(--ok)}.finished{color:var(--ok)}.error{color:var(--bad)}.stopped,.loading,.starting{color:var(--warn)}
.bar{height:16px;background:var(--line);border-radius:8px;overflow:hidden;margin:12px 0 6px}
.bar>i{display:block;height:100%;background:var(--accent);transition:width .6s}
.big{font-size:26px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.v{font-size:20px;font-weight:650}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600}.terms{color:var(--accent)}.err{color:var(--bad)}
.hist{display:flex;align-items:flex-end;gap:6px;height:90px}.hist div{flex:1;text-align:center;font-size:11px;color:var(--mute)}
.hist b{display:block;background:var(--accent);border-radius:3px 3px 0 0;min-height:1px;margin-bottom:3px}
.msg{margin-top:8px;color:var(--bad);font-size:13px}
@media(max-width:560px){.big{font-size:22px}td:nth-child(3){display:none}th:nth-child(3){display:none}}
</style></head><body><main>
<h1>SoilVoc extraction progress</h1>
<div class="sub" id="sub">waiting for progress.json …</div>
<div class="card">
  <div class="row"><span class="pill" id="status">-</span><span class="big" id="pct">0%</span>
  <span id="count" style="color:var(--mute)"></span></div>
  <div class="bar"><i id="fill" style="width:0"></i></div>
  <div class="row" style="color:var(--mute);font-size:13px"><span id="eta"></span></div>
  <div class="msg" id="msg"></div>
</div>
<div class="grid card" id="stats"></div>
<div class="card"><div class="k" style="margin-bottom:8px">Terms chosen per record</div><div class="hist" id="hist"></div></div>
<div class="card"><div class="k" style="margin-bottom:8px">Most chosen concepts</div><table id="top"></table></div>
<div class="card"><div class="k" style="margin-bottom:8px">Latest records</div><table id="recent"></table></div>
</main>
<script>
const $=id=>document.getElementById(id);
const fmt=s=>{if(s==null)return'–';s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h?`${h} h ${m} min`:m?`${m} min ${s%60} s`:`${s} s`};
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function tick(){
 try{
  const p=await (await fetch('/api/progress')).json();
  if(p.error){$('sub').textContent=p.error;return}
  $('sub').textContent=`${p.provider} · ${p.model} · ${p.workers} worker(s) · source: ${p.source} · started ${p.started_at}`;
  const st=$('status');st.textContent=p.status;st.className='pill '+p.status;
  const pct=p.total?100*p.done/p.total:0;
  $('pct').textContent=pct.toFixed(1)+'%';$('count').textContent=`${p.done.toLocaleString()} of ${p.total.toLocaleString()} records`;
  $('fill').style.width=pct+'%';
  $('eta').textContent=p.status==='finished'?`finished in ${fmt(p.elapsed_seconds)}`:`elapsed ${fmt(p.elapsed_seconds)} · remaining about ${fmt(p.eta_seconds)}`;
  $('msg').textContent=p.message&&p.status!=='running'?p.message:'';
  const cell=(k,v)=>`<div><div class="k">${k}</div><div class="v">${v}</div></div>`;
  $('stats').innerHTML=cell('Records / min',p.records_per_minute)+cell('Avg terms / record',p.avg_terms)+
   cell('Records with no term',p.empty.toLocaleString())+cell('Invalid terms dropped',p.invalid.toLocaleString())+
   cell('Errors (retried on restart)',p.errors.toLocaleString())+cell('Terms chosen',p.chosen.toLocaleString());
  const h=p.terms_histogram||{},keys=[...Array(11).keys()].map(String),max=Math.max(1,...keys.map(k=>h[k]||0));
  $('hist').innerHTML=keys.map(k=>`<div><b style="height:${70*(h[k]||0)/max}px"></b>${k==='10'?'10+':k}</div>`).join('');
  $('recent').innerHTML='<tr><th>Title</th><th>Chosen concepts</th><th>s</th></tr>'+[...p.recent].reverse().map(r=>
   `<tr><td>${esc(r.title||r.id)}</td><td class="${r.error?'err':'terms'}">${r.error?esc(r.error):esc(r.terms.join(', '))||'<span style="color:var(--mute)">none</span>'}</td><td>${r.seconds}</td></tr>`).join('');
  const t=await (await fetch('/api/top')).json();
  $('top').innerHTML='<tr><th>Concept</th><th>Records</th></tr>'+t.map(x=>`<tr><td>${esc(x[0])}</td><td>${x[1]}</td></tr>`).join('');
 }catch(e){$('sub').textContent='cannot read progress: '+e}
}
tick();setInterval(tick,3000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    out = ROOT / "reports" / "llm_extraction"
    cache = {"mtime": None, "top": []}

    def send(self, body, ctype):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/progress":
            f = self.out / "progress.json"
            self.send(f.read_text(encoding="utf-8") if f.exists() else json.dumps({"error": f"no progress.json in {self.out} yet; start the extraction"}), "application/json")
        elif self.path == "/api/top":
            self.send(json.dumps(self.top()), "application/json")
        else:
            self.send_error(404)

    def top(self):
        f = self.out / "results.jsonl"
        if not f.exists():
            return []
        mtime = f.stat().st_mtime
        if self.cache["mtime"] != mtime:
            c = Counter()
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        for t in json.loads(line)["terms"]:
                            c[t["label"]] += 1
                    except (json.JSONDecodeError, KeyError):
                        pass  # a line that is still being written
            self.cache.update(mtime=mtime, top=c.most_common(15))
        return self.cache["top"]

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "llm_extraction"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to watch from another computer")
    a = ap.parse_args()
    Handler.out = Path(a.out)
    print(f"watching {Handler.out}\nopen http://{'localhost' if a.host == '127.0.0.1' else a.host}:{a.port}   (Ctrl+C to stop)")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
