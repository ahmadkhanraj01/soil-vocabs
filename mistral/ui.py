"""Local dashboard for mistral/extract.py and mistral/estimate.py. Reads files only (no API, no database).

  python mistral/ui.py                                   # watches mistral/runs/extract
  python mistral/ui.py --out mistral/runs/estimate-mistral-small-latest

Open http://localhost:8766 . It shows a progress bar, estimated time left, tokens, cost so far and the
projected cost of the full run; after estimate.py it also shows the estimate table.
"""
import argparse
import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mistral extraction</title>
<style>
:root{--bg:#f7f6f3;--card:#fff;--ink:#241f1a;--mute:#6f675d;--line:#e4dfd6;--accent:#d9541e;--ok:#2f6b3a;--warn:#b26a00;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#181512;--card:#221e1a;--ink:#efe9e1;--mute:#a1978a;--line:#363029;--accent:#f08a5d;--ok:#6fbf7d;--warn:#e0a040;--bad:#f0807a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mute);font-size:13px;margin-bottom:16px;word-break:break-all}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.running,.finished{color:var(--ok)}.error{color:var(--bad)}.stopped,.starting{color:var(--warn)}
.bar{height:16px;background:var(--line);border-radius:8px;overflow:hidden;margin:12px 0 6px}
.bar>i{display:block;height:100%;background:var(--accent);transition:width .6s}
.big{font-size:26px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.v{font-size:20px;font-weight:650}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600}.terms{color:var(--accent)}.err{color:var(--bad)}
.msg{margin-top:8px;color:var(--bad);font-size:13px}.note{color:var(--mute);font-size:12px;margin-top:8px}
@media(max-width:560px){.big{font-size:22px}}
</style></head><body><main>
<h1>Mistral extraction</h1>
<div class="sub" id="sub">waiting for progress.json …</div>
<div class="card">
  <div class="row"><span class="pill" id="status">-</span><span class="big" id="pct">0%</span><span id="count" style="color:var(--mute)"></span></div>
  <div class="bar"><i id="fill" style="width:0"></i></div>
  <div style="color:var(--mute);font-size:13px" id="eta"></div>
  <div class="msg" id="msg"></div>
</div>
<div class="grid card" id="stats"></div>
<div class="card" id="estcard" style="display:none"><div class="k" style="margin-bottom:8px">Estimate (random sample)</div><table id="est"></table><div class="note" id="estnote"></div></div>
<div class="card"><div class="k" style="margin-bottom:8px">Most chosen concepts</div><table id="top"></table></div>
<div class="card"><div class="k" style="margin-bottom:8px">Latest records</div><table id="recent"></table></div>
</main>
<script>
const $=id=>document.getElementById(id);
const fmt=s=>{if(s==null)return'–';s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h?`${h} h ${m} min`:m?`${m} min ${s%60} s`:`${s} s`};
const usd=x=>x==null?'–':'$'+(x<1?x.toFixed(4):x.toFixed(2));
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function tick(){
 try{
  const p=await (await fetch('/api/progress')).json();
  if(p.error){$('sub').textContent=p.error;return}
  $('sub').textContent=`${p.kind==='estimate'?'ESTIMATE':'EXTRACT'} · ${p.model} · ${p.workers} worker(s) · ${p.source}`;
  const st=$('status');st.textContent=p.status;st.className='pill '+p.status;
  const pct=p.total?100*p.done/p.total:0;
  $('pct').textContent=pct.toFixed(1)+'%';$('count').textContent=`${p.done.toLocaleString()} of ${p.total.toLocaleString()} records`;
  $('fill').style.width=pct+'%';
  $('eta').textContent=p.status==='finished'?`finished in ${fmt(p.elapsed_seconds)}`:`elapsed ${fmt(p.elapsed_seconds)} · remaining about ${fmt(p.eta_seconds)}`;
  $('msg').textContent=p.message&&p.status!=='running'?p.message:'';
  const c=(k,v)=>`<div><div class="k">${k}</div><div class="v">${v}</div></div>`;
  $('stats').innerHTML=c('Cost so far',usd(p.cost_usd))+c('Cost per record',usd(p.cost_per_record_usd))+
   c(`Projected, all ${p.target_total.toLocaleString()} records`,usd(p.projected_cost_usd))+c('Projected time, all',fmt(p.projected_seconds))+
   c('Records / min',p.records_per_minute)+c('Input tokens',p.tokens_in.toLocaleString())+c('Output tokens',p.tokens_out.toLocaleString())+
   c('Avg terms / record',p.avg_terms)+c('No term',p.empty.toLocaleString())+c('Invalid terms dropped',p.invalid.toLocaleString())+
   c('Rate-limit replies (429)',p.rate_limited)+c('Errors (retried on restart)',p.errors);
  $('recent').innerHTML='<tr><th>Title</th><th>Chosen concepts</th><th>s</th><th>USD</th></tr>'+[...p.recent].reverse().map(r=>
   `<tr><td>${esc(r.title||r.id)}</td><td class="${r.error?'err':'terms'}">${r.error?esc(r.error):esc(r.terms.join(', '))||'none'}</td><td>${r.seconds}</td><td>${r.cost_usd?r.cost_usd.toFixed(5):''}</td></tr>`).join('');
  const t=await (await fetch('/api/top')).json();
  $('top').innerHTML='<tr><th>Concept</th><th>Records</th></tr>'+t.map(x=>`<tr><td>${esc(x[0])}</td><td>${x[1]}</td></tr>`).join('');
  const e=await (await fetch('/api/estimate')).json();
  if(e.table){
   $('estcard').style.display='';
   $('est').innerHTML='<tr><th>Records</th><th>Time</th><th>Per record</th><th>Input tok.</th><th>Output tok.</th><th>Cost</th><th>Avg terms</th></tr>'+
    e.table.map(r=>`<tr><td>${r.records}</td><td>${fmt(r.seconds)}</td><td>${r.seconds_per_record} s</td><td>${r.tokens_in.toLocaleString()}</td><td>${r.tokens_out.toLocaleString()}</td><td>${usd(r.cost_usd)}</td><td>${r.avg_terms}</td></tr>`).join('')+
    `<tr><td><b>All ${e.projection.records.toLocaleString()}</b></td><td><b>${fmt(e.projection.seconds)}</b></td><td></td><td></td><td></td><td><b>${usd(e.projection.cost_usd)}</b></td><td></td></tr>`;
   $('estnote').textContent=`Range ${usd(e.projection.cost_usd_low)} to ${usd(e.projection.cost_usd_high)} · ${e.workers} workers · prices: ${e.prices_checked}`;
  }
 }catch(err){$('sub').textContent='cannot read progress: '+err}
}
tick();setInterval(tick,2500);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    out = HERE / "runs" / "extract"
    cache = {"mtime": None, "top": []}

    def send(self, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def file_or(self, name, default):
        f = self.out / name
        return f.read_text(encoding="utf-8") if f.exists() else json.dumps(default)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/progress":
            self.send(self.file_or("progress.json", {"error": f"no progress.json in {self.out} yet; start a run"}))
        elif self.path == "/api/estimate":
            self.send(self.file_or("estimate.json", {}))
        elif self.path == "/api/top":
            self.send(json.dumps(self.top()))
        else:
            self.send_error(404)

    def top(self):
        f = self.out / "results.jsonl"
        if not f.exists():
            return []
        m = f.stat().st_mtime
        if self.cache["mtime"] != m:
            c = Counter()
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    for t in json.loads(line)["terms"]:
                        c[t["label"]] += 1
                except (json.JSONDecodeError, KeyError):
                    pass
            self.cache.update(mtime=m, top=c.most_common(15))
        return self.cache["top"]

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "runs" / "extract"))
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    Handler.out = Path(a.out)
    print(f"watching {Handler.out}\nopen http://{'localhost' if a.host == '127.0.0.1' else a.host}:{a.port}   (Ctrl+C to stop)")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
