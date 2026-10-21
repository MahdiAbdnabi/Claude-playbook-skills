#!/usr/bin/env python3
"""
build_diagram_page.py — render a diagram JSON into ONE interactive HTML page:
pan/zoom · click a node or edge → evidence panel (claim, [src:], tags) · level switch
(hld → design → tracking) · tag filter (hide [PLANNED], highlight GAP/DRIFT/PROTECTED) ·
lens toggle (dim what the lens does not care about) · flow step-through (walks a D6/D8 flow
and opens each step's evidence). Layout is done by Mermaid; this page adds the interaction.

Usage:
    python3 build_diagram_page.py diagrams/<batch>.json [--out diagrams/<batch>.html] [--offline]
    --offline inlines nothing extra but switches the Mermaid <script> to a local ./mermaid.min.js
    you place next to the page (for hosts without internet).

Diagram JSON schema (see assets/diagram.example.json):
{
  "system": "name", "scope": "batch or portfolio-wide", "version": "v1, date",
  "maturity": "N nodes · E edges · x% [src] · g [GAP] · p [PLANNED]",
  "lenses": ["ARCH","DEV","QA","BA"],
  "nodes": [ {"id":"api","label":"Movement API","level":"hld",          # hld | design | tracking
              "kind":"container",                                      # actor|system|container|component|entity|screen|step|rule|test|external
              "parent":"",                                              # optional: id of the enclosing node (drawn as a subgraph)
              "claim":"ASP.NET Core host for movement processing",
              "src":"Program.cs#Main", "tags":["src"],                  # tags: src|gap|planned|drift|protected|untested|tested|stale
              "lenses":["ARCH","DEV"]} ],
  "edges": [ {"id":"e1","from":"ui","to":"api","label":"REST/JSON","level":"hld",
              "claim":"Angular calls the API over HTTPS", "src":"movement.service.ts#post",
              "tags":["src"], "lenses":["ARCH","DEV"]} ],
  "flows": [ {"id":"F-01","name":"Arrival — first time","level":"design",     # design (D6) | tracking (D8)
              "steps":[ {"node":"scan","edge":"e3","claim":"Officer scans passport","src":"ScanController.cs#Post",
                         "rule":"BR-003","test":"[tested: ScanTests.HappyPath]","tags":["src","tested"]} ]} ]
}
Levels are cumulative: the "design" view shows hld+design elements; "tracking" shows everything.
"""
import argparse, html, json, os, re

LEVELS = ["hld", "design", "tracking"]
LEVEL_LABEL = {"hld": "High-level design", "design": "Design", "tracking": "Full tracking"}
SHAPE = {"actor": ("([", "])"), "system": ("[[", "]]"), "container": ("[", "]"), "component": ("(", ")"),
         "entity": ("[(", ")]"), "screen": ("[/", "/]"), "step": ("[", "]"), "rule": ("{{", "}}"),
         "test": ("[", "]"), "external": ("[[", "]]")}


def mid(s):  # mermaid-safe id
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def lbl(s):
    return html.escape(s).replace('"', "&quot;")


def mermaid_for(d, upto):
    """Build one Mermaid flowchart containing every element whose level index <= upto."""
    ok = {l for i, l in enumerate(LEVELS) if i <= LEVELS.index(upto)}
    nodes = [n for n in d["nodes"] if n.get("level", "hld") in ok]
    ids = {n["id"] for n in nodes}
    edges = [e for e in d["edges"] if e.get("level", "hld") in ok and e["from"] in ids and e["to"] in ids]
    out = ["flowchart LR"]
    children = {}
    for n in nodes:
        children.setdefault(n.get("parent") or "", []).append(n)

    def emit(n, ind):
        o, c = SHAPE.get(n.get("kind", "container"), ("[", "]"))
        tagmark = "".join({"gap": " ⚠", "drift": " ⇄", "protected": " ★", "planned": " ◌", "untested": " ✗"}.get(t, "") for t in n.get("tags", []))
        line = f'{"  " * ind}{mid(n["id"])}{o}"{lbl(n["label"])}{tagmark}"{c}'
        out.append(line)
        if n["id"] in children:
            pass

    def emit_group(parent, ind):
        for n in children.get(parent, []):
            if n["id"] in children:
                out.append(f'{"  " * ind}subgraph {mid(n["id"])}_g["{lbl(n["label"])}"]')
                emit(n, ind + 1); emit_group(n["id"], ind + 1)
                out.append(f'{"  " * ind}end')
            else:
                emit(n, ind)
    emit_group("", 1)
    for e in edges:
        arrow = "-.->" if "gap" in e.get("tags", []) else ("-->" if "planned" not in e.get("tags", []) else "-.->")
        out.append(f'  {mid(e["from"])} {arrow}|"{lbl(e.get("label", ""))}"| {mid(e["to"])}')
    # classes
    for n in nodes:
        cls = next((t for t in ("gap", "drift", "protected", "planned", "untested", "stale") if t in n.get("tags", [])), "src")
        out.append(f"  class {mid(n['id'])} t_{cls}")
    out.append("  classDef t_src stroke:#0E8F84,stroke-width:1.5px")
    out.append("  classDef t_gap stroke:#C4462C,stroke-dasharray:5 4,stroke-width:2px")
    out.append("  classDef t_drift stroke:#B86E0A,stroke-width:3px,stroke-dasharray:2 2")
    out.append("  classDef t_protected stroke:#B86E0A,stroke-width:3px")
    out.append("  classDef t_planned stroke:#3A5BC7,stroke-dasharray:2 4,fill:transparent")
    out.append("  classDef t_untested stroke:#C4462C,stroke-width:2px")
    out.append("  classDef t_stale stroke:#7A4FC7,stroke-dasharray:6 2")
    out.append("  classDef dim opacity:0.25")
    out.append("  classDef hot stroke-width:4px,stroke:#E8A33D")
    return "\n".join(out), [n["id"] for n in nodes], [e["id"] for e in edges]


CSS = """
:root{--bg:#F6F7F9;--surface:#fff;--surface-2:#EEF1F5;--border:#D9DEE6;--text:#1B2230;--text-2:#3E4756;--text-3:#8A93A3;--teal:#0E8F84;--amber:#B86E0A;--coral:#C4462C;--blue:#3A5BC7;--violet:#7A4FC7;
--sans:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;--mono:'IBM Plex Mono',SF Mono,Consolas,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#12151C;--surface:#1B212C;--surface-2:#212837;--border:#2A3140;--text:#E8EAED;--text-2:#A6AEBD;--text-3:#5A6272;--teal:#4FD1C5;--amber:#E8A33D;--coral:#E8735C;--blue:#7C9CE8;--violet:#B48EE8}}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;height:100vh;display:flex;flex-direction:column;overflow:hidden}
header{padding:12px 16px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;flex-wrap:wrap;gap:10px;align-items:center}
header h1{font-size:16px;margin-right:8px}.hdr{font-family:var(--mono);font-size:11px;color:var(--text-3)}
.grp{display:flex;gap:4px;align-items:center;font-size:12px;color:var(--text-3)}.grp b{margin-right:4px}
button,.btn{font-family:var(--sans);font-size:12px;padding:5px 10px;border-radius:6px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-2);cursor:pointer}
button.on{color:var(--teal);border-color:var(--teal);background:rgba(14,143,132,.1)}button.warn.on{color:var(--coral);border-color:var(--coral)}
main{flex:1;display:flex;min-height:0}#canvas{flex:1;overflow:hidden;position:relative;cursor:grab;background-image:linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px);background-size:32px 32px;opacity:.98}
#canvas.grabbing{cursor:grabbing}#stage{transform-origin:0 0;position:absolute;left:0;top:0}#stage svg{max-width:none!important;height:auto}
aside{width:360px;border-left:1px solid var(--border);background:var(--surface);overflow-y:auto;padding:16px}aside h2{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-3);margin:0 0 8px}
aside h3{font-size:15px;margin:4px 0 10px}aside p{color:var(--text-2);margin:6px 0;line-height:1.5}.tag{font-family:var(--mono);font-size:11px;padding:1px 6px;border-radius:4px;border:1px solid;margin-right:4px;white-space:nowrap;display:inline-block;margin-bottom:4px}
.t-src,.t-tested{color:var(--teal);border-color:var(--teal)}.t-gap,.t-untested{color:var(--coral);border-color:var(--coral)}.t-drift,.t-protected{color:var(--amber);border-color:var(--amber)}.t-planned{color:var(--blue);border-color:var(--blue)}.t-stale{color:var(--violet);border-color:var(--violet)}
code{font-family:var(--mono);font-size:12px;background:var(--surface-2);padding:1px 5px;border-radius:4px;word-break:break-all}.muted{color:var(--text-3);font-size:12px}
.flowbar{padding:8px 16px;border-top:1px solid var(--border);background:var(--surface);display:flex;gap:8px;align-items:center;font-size:12px;flex-wrap:wrap}select{font-family:var(--sans);font-size:12px;padding:5px 8px;border-radius:6px;border:1px solid var(--border);background:var(--surface-2);color:var(--text)}
.step{background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin:8px 0}.step.on{border-color:var(--amber)}.legend{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 14px}
footer{padding:6px 16px;border-top:1px solid var(--border);font-size:11px;color:var(--text-3);background:var(--surface)}
.node,.edgeLabel,.edgePath{cursor:pointer}@media (max-width:900px){aside{width:100%;position:absolute;bottom:0;max-height:45vh;border-left:none;border-top:1px solid var(--border)}}
"""


def build(d, offline=False):
    views = {}
    for lv in LEVELS:
        src, nids, eids = mermaid_for(d, lv)
        views[lv] = {"src": src, "nodes": nids, "edges": eids}
    max_level = max((LEVELS.index(n.get("level", "hld")) for n in d["nodes"]), default=0)
    avail = LEVELS[: max_level + 1]
    data = {"nodes": {n["id"]: n for n in d["nodes"]}, "edges": {e["id"]: e for e in d["edges"]},
            "flows": d.get("flows", []), "views": views, "lenses": d.get("lenses", []), "levels": avail}
    mermaid_src = "./mermaid.min.js" if offline else "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
    title = f"{d.get('system', 'System')} — diagrams — {d.get('scope', '')}"
    lens_btns = "".join(f'<button data-lens="{html.escape(l)}">{html.escape(l)}</button>' for l in d.get("lenses", []))
    level_btns = "".join(f'<button data-level="{lv}" class="{"on" if i == len(avail) - 1 else ""}">{LEVEL_LABEL[lv]}</button>' for i, lv in enumerate(avail))
    flow_opts = "".join(f'<option value="{html.escape(f["id"])}">{html.escape(f["id"])} — {html.escape(f["name"])}</option>' for f in d.get("flows", []))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet"><style>{CSS}</style>
<script src="{mermaid_src}"></script></head><body>
<header><h1>{html.escape(d.get('system', 'System'))} — diagrams</h1><span class="hdr">{html.escape(d.get('scope', ''))} · {html.escape(d.get('version', ''))} · {html.escape(d.get('maturity', ''))}</span>
<span class="grp"><b>Level</b>{level_btns}</span>
<span class="grp"><b>Lens</b><button data-lens="" class="on">All</button>{lens_btns}</span>
<span class="grp"><b>Tags</b><button data-tag="planned" class="on">show [PLANNED]</button><button data-tag="hl-gap" class="warn">highlight GAP</button><button data-tag="hl-drift" class="warn">highlight DRIFT</button><button data-tag="hl-protected" class="warn">highlight PROTECTED</button></span>
<span class="grp"><button id="fit">Fit</button></span></header>
<main><div id="canvas"><div id="stage"></div></div>
<aside><h2>Evidence</h2><div class="legend"><span class="tag t-src">[src]</span><span class="tag t-gap">[GAP] ⚠ dashed</span><span class="tag t-drift">[DRIFT] ⇄</span><span class="tag t-planned">[PLANNED] ◌ hollow</span><span class="tag t-protected">[PROTECTED] ★</span><span class="tag t-untested">[UNTESTED] ✗</span></div>
<div id="panel"><p class="muted">Click a node or an edge to see the claim behind it, its source citation and tags. Use the level switch to go from context down to per-step tracking, the lens buttons to dim what a role does not need, and the flow bar to step through a journey.</p></div></aside></main>
<div class="flowbar"><b>Flow</b><select id="flow"><option value="">— pick a flow —</option>{flow_opts}</select><button id="prev">◀</button><span id="stepno" class="muted">—</span><button id="next">▶</button><button id="stop">Stop</button></div>
<footer>Interactive view generated by build_diagram_page.py from the diagram JSON. Every element shown is a claim in the corpus; the page adds nothing. Mermaid loaded from {'local file' if offline else 'CDN'}.</footer>
<script id="data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>
<script>
(function(){{
const D=JSON.parse(document.getElementById('data').textContent);
let level=D.levels[D.levels.length-1], lens='', showPlanned=true, hl={{gap:false,drift:false,protected:false}};
let flow=null, stepIdx=-1;
const stage=document.getElementById('stage'), canvas=document.getElementById('canvas'), panel=document.getElementById('panel');
let tx=20,ty=20,sc=1, drag=null;
mermaid.initialize({{startOnLoad:false, securityLevel:'loose', theme:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'neutral'), flowchart:{{useMaxWidth:false, htmlLabels:true}}}});
function mid(s){{return s.replace(/[^A-Za-z0-9_]/g,'_')}}
function tagHtml(tags){{return (tags||[]).map(t=>`<span class="tag t-${{t}}">[${{t==='src'?'src':t.toUpperCase()}}]</span>`).join('')}}
function show(kind,id){{
  const o=kind==='node'?D.nodes[id]:D.edges[id]; if(!o) return;
  const title=kind==='node'?o.label:`${{D.nodes[o.from]?.label||o.from}} → ${{D.nodes[o.to]?.label||o.to}}`;
  panel.innerHTML=`<h3>${{esc(title)}}</h3><p class="muted">${{kind}} · ${{o.kind||''}} · level ${{o.level||'hld'}}</p><p>${{esc(o.claim||'')}}</p>`+
   (o.src?`<p><code>[src: ${{esc(o.src)}}]</code></p>`:'<p><span class="tag t-gap">[GAP]</span> no citation</p>')+`<p>${{tagHtml(o.tags)}}</p>`+
   (o.lenses&&o.lenses.length?`<p class="muted">Lenses: ${{o.lenses.join(', ')}}</p>`:'')+(o.notes?`<p>${{esc(o.notes)}}</p>`:'');
}}
function esc(s){{return String(s).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
async function render(){{
  const v=D.views[level]; const {{svg}}=await mermaid.render('m'+Date.now(), v.src); stage.innerHTML=svg;
  const S=stage.querySelector('svg');
  // click binding
  S.querySelectorAll('.node').forEach(el=>{{ const id=Object.keys(D.nodes).find(k=>el.id.includes('-'+mid(k)+'-')||el.id.endsWith(mid(k))||el.id.includes(mid(k)+'-')); if(!id) return; el.dataset.nid=id; el.addEventListener('click',()=>show('node',id)); }});
  const paths=S.querySelectorAll('.edgePath'), labels=S.querySelectorAll('.edgeLabel');
  v.edges.forEach((eid,i)=>{{ if(paths[i]){{paths[i].dataset.eid=eid; paths[i].addEventListener('click',()=>show('edge',eid));}} if(labels[i]){{labels[i].dataset.eid=eid; labels[i].addEventListener('click',()=>show('edge',eid));}} }});
  applyFilters(); apply();
}}
function applyFilters(){{
  const S=stage.querySelector('svg'); if(!S) return;
  S.querySelectorAll('.node').forEach(el=>{{ const n=D.nodes[el.dataset.nid]; if(!n) return; el.classList.remove('dim','hot'); el.style.display='';
    if(!showPlanned && (n.tags||[]).includes('planned')) el.style.display='none';
    if(lens && !(n.lenses||[]).includes(lens)) el.classList.add('dim');
    if((hl.gap&&(n.tags||[]).includes('gap'))||(hl.drift&&(n.tags||[]).includes('drift'))||(hl.protected&&(n.tags||[]).includes('protected'))) el.classList.add('hot'); }});
  S.querySelectorAll('.edgePath,.edgeLabel').forEach(el=>{{ const e=D.edges[el.dataset.eid]; if(!e) return; el.classList.remove('dim'); el.style.display='';
    if(!showPlanned && (e.tags||[]).includes('planned')) el.style.display='none';
    if(lens && !(e.lenses||[]).includes(lens)) el.classList.add('dim'); }});
  if(flow&&stepIdx>=0){{ const st=flow.steps[stepIdx]; S.querySelectorAll('.node').forEach(el=>{{ if(el.dataset.nid===st.node) el.classList.add('hot'); }}); S.querySelectorAll('.edgePath').forEach(el=>{{ if(el.dataset.eid===st.edge) el.classList.add('hot'); }}); }}
}}
function apply(){{ stage.style.transform=`translate(${{tx}}px,${{ty}}px) scale(${{sc}})`; }}
canvas.addEventListener('wheel',e=>{{ e.preventDefault(); const r=canvas.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top; const f=e.deltaY<0?1.1:0.9; tx=mx-(mx-tx)*f; ty=my-(my-ty)*f; sc*=f; apply(); }},{{passive:false}});
canvas.addEventListener('mousedown',e=>{{ if(e.target.closest('.node,.edgeLabel,.edgePath')) return; drag={{x:e.clientX-tx,y:e.clientY-ty}}; canvas.classList.add('grabbing'); }});
window.addEventListener('mousemove',e=>{{ if(!drag) return; tx=e.clientX-drag.x; ty=e.clientY-drag.y; apply(); }});
window.addEventListener('mouseup',()=>{{ drag=null; canvas.classList.remove('grabbing'); }});
document.getElementById('fit').addEventListener('click',()=>{{ const S=stage.querySelector('svg'); if(!S) return; const b=S.getBBox(); const r=canvas.getBoundingClientRect(); sc=Math.min((r.width-40)/b.width,(r.height-40)/b.height,1.5); tx=20; ty=20; apply(); }});
document.querySelectorAll('[data-level]').forEach(b=>b.addEventListener('click',()=>{{ document.querySelectorAll('[data-level]').forEach(x=>x.classList.remove('on')); b.classList.add('on'); level=b.dataset.level; render(); }}));
document.querySelectorAll('[data-lens]').forEach(b=>b.addEventListener('click',()=>{{ document.querySelectorAll('[data-lens]').forEach(x=>x.classList.remove('on')); b.classList.add('on'); lens=b.dataset.lens; applyFilters(); }}));
document.querySelectorAll('[data-tag]').forEach(b=>b.addEventListener('click',()=>{{ b.classList.toggle('on'); const t=b.dataset.tag; if(t==='planned') showPlanned=b.classList.contains('on'); else hl[t.replace('hl-','')]=b.classList.contains('on'); applyFilters(); }}));
const sel=document.getElementById('flow'), stepno=document.getElementById('stepno');
function showStep(){{ if(!flow){{stepno.textContent='—';return;}} const st=flow.steps[stepIdx]; stepno.textContent=`${{flow.id}} · step ${{stepIdx+1}}/${{flow.steps.length}}`;
  panel.innerHTML=`<h3>${{esc(flow.name)}}</h3><p class="muted">${{flow.id}} · ${{flow.level||'design'}}</p>`+flow.steps.map((s,i)=>`<div class="step ${{i===stepIdx?'on':''}}"><b>${{i+1}}.</b> ${{esc(s.claim)}}<br>${{s.src?`<code>[src: ${{esc(s.src)}}]</code>`:'<span class="tag t-gap">[GAP]</span>'}} ${{s.rule?`<code>${{esc(s.rule)}}</code>`:''}} ${{s.test?`<code>${{esc(s.test)}}</code>`:''}}<br>${{tagHtml(s.tags)}}</div>`).join('');
  const need=flow.level||'design'; if(D.levels.indexOf(need)>D.levels.indexOf(level)){{ level=need; document.querySelectorAll('[data-level]').forEach(x=>x.classList.toggle('on',x.dataset.level===level)); render(); }} else applyFilters(); }}
sel.addEventListener('change',()=>{{ flow=D.flows.find(f=>f.id===sel.value)||null; stepIdx=flow?0:-1; showStep(); }});
document.getElementById('next').addEventListener('click',()=>{{ if(!flow) return; stepIdx=Math.min(stepIdx+1,flow.steps.length-1); showStep(); }});
document.getElementById('prev').addEventListener('click',()=>{{ if(!flow) return; stepIdx=Math.max(stepIdx-1,0); showStep(); }});
document.getElementById('stop').addEventListener('click',()=>{{ flow=null; stepIdx=-1; sel.value=''; stepno.textContent='—'; applyFilters(); }});
render().then(()=>document.getElementById('fit').click());
}})();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json"); ap.add_argument("--out", default=None); ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.json, encoding="utf-8"))
    for k in ("nodes", "edges"): d.setdefault(k, [])
    out = a.out or os.path.splitext(a.json)[0] + ".html"
    open(out, "w", encoding="utf-8").write(build(d, a.offline))
    untagged = [n["id"] for n in d["nodes"] if not n.get("src") and "gap" not in n.get("tags", []) and "planned" not in n.get("tags", [])]
    print(f"wrote {out}: {len(d['nodes'])} nodes, {len(d['edges'])} edges, {len(d.get('flows', []))} flows")
    if untagged:
        print(f"WARNING {len(untagged)} node(s) have neither [src] nor a GAP/PLANNED tag — Phase 5 will fail them: {', '.join(untagged)}")


if __name__ == "__main__":
    main()
