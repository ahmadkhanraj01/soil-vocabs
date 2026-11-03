"""Check validate.soilvoc_types on stage against reports/soilvoc_hierarchy.json (read-only).

Compares names, levels, tree parents, children, descendants, multi-parent lists and
detached procedure codes. Usage: python3 scripts/check_soilvoc_types_vs_json.py
"""
import json, csv, psycopg2
from collections import defaultdict, Counter
from dotenv import dotenv_values
J=json.load(open('reports/soilvoc_hierarchy.json'))
j={}  # uri -> dict
def walk(n, parent):
    j[n['uri']]=dict(name=n['name'],level=n['level'],parent=parent,
        children={c['uri'] for c in n.get('children',[])},desc=n['descendants'],
        other=set(n.get('other_parents',[])))
    for c in n.get('children',[]): walk(c,n['uri'])
for t in J['children']: walk(t,None)
det={d['uri']:d for d in J['detached_procedure_codes']}
e=dotenv_values('.env'); g=lambda k:e[k+'1']
c=psycopg2.connect(host=g('DB_HOST'),port=g('DB_PORT'),dbname=g('DB_NAME'),user=g('DB_USER'),password=g('DB_PASSWORD'))
c.set_session(readonly=True); cur=c.cursor()
cur.execute("select current_database(), current_schema()"); print('DB:',cur.fetchone())
cur.execute("select code,level,parent_code,name from validate.soilvoc_types")
d={code:dict(level=l,parent=p,name=n) for code,l,p,n in cur.fetchall()}
kids=defaultdict(set)
for code,v in d.items():
    if v['parent']: kids[v['parent']].add(code)
def desc(u): return sum(1+desc(k) for k in kids[u])
name_of={u:v['name'] for u,v in d.items()}
multi={r['uri']:set(r['all_parents'].split(' | ')) for r in csv.DictReader(open('reports/soilvoc_levels_vs_db/multi_parent_concepts.csv'))}
print('JSON: in hierarchy',len(j),'(declared',J['concepts_in_hierarchy'],') detached',len(det),'total',len(j)+len(det))
print('DB  : total',len(d),'with level',sum(1 for v in d.values() if v['level']),'detached',sum(1 for v in d.values() if v['level'] is None))
print('URIs only in JSON:',len(set(j)|set(det))-len((set(j)|set(det))&set(d)),' only in DB:',len(set(d)-set(j)-set(det)))
mis=Counter(); ex=defaultdict(list)
def bad(k,u,info):
    mis[k]+=1
    if len(ex[k])<5: ex[k].append((name_of.get(u,u),info))
for u,v in j.items():
    x=d.get(u)
    if not x: bad('missing in DB',u,''); continue
    if x['name']!=v['name']: bad('name',u,(x['name'],v['name']))
    if x['level']!=v['level']: bad('level',u,(x['level'],v['level']))
    if x['parent']!=v['parent']: bad('parent',u,(name_of.get(x['parent']),name_of.get(v['parent'])))
    if kids[u]!=v['children']: bad('children',u,(len(kids[u]),len(v['children'])))
    if desc(u)!=v['desc']: bad('descendants',u,(desc(u),v['desc']))
    allp_json={name_of.get(v['parent'])}|v['other'] if v['parent'] else set()
    allp_db={name_of[p] for p in multi.get(u,set()) if p in name_of} or ({name_of[x['parent']]} if x['parent'] else set())
    if allp_json!=allp_db: bad('all parents',u,(sorted(allp_db),sorted(allp_json)))
for u,v in det.items():
    x=d.get(u)
    if not x: bad('detached missing in DB',u,''); continue
    if x['level'] is not None: bad('detached has level in DB',u,x['level'])
    if name_of.get(x['parent']) != v.get('parent'): bad('detached parent',u,(name_of.get(x['parent']),v.get('parent')))
    if x['name']!=v['name']: bad('detached name',u,(x['name'],v['name']))
print('per level JSON',sorted(Counter(v['level'] for v in j.values()).items()))
print('per level DB  ',sorted(Counter(v['level'] for v in d.values() if v['level']).items()))
print('top concepts JSON',len(J['children']),'DB',sum(1 for v in d.values() if v['level']==1))
print('parent-child edges JSON',sum(len(v['children']) for v in j.values())+sum(1 for v in det.values() if v.get('parent')),'DB',sum(len(s) for s in kids.values()))
print('multi-parent JSON',sum(1 for v in j.values() if v['other']),'DB csv',len(multi))
print('detached with a parent in JSON',sum(1 for v in det.values() if v.get('parent')))
print('MISMATCHES:',dict(mis) or 'none')
for k,v in ex.items(): print(' ',k,v)
