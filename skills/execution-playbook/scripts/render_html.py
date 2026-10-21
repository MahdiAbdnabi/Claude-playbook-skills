#!/usr/bin/env python3
"""
render_html.py — render every Markdown file under the playbook folder (PLAYBOOK.md, CLAUDE.md,
work-packages/, adr/, review/, DECISIONS/GAPS/RISKS) into HTML pages with a sidebar index and
tag highlighting. TRACKER.md, USAGE.md and decisions/DC-*.md have their own richer renderers
(build_tracker.py, build_decision_card.py) and are linked, not re-rendered.

Usage:
    python3 render_html.py PLAYBOOK_DIR [--out DIR] [--title "Task name"]
Requires:  pip install markdown
"""
import argparse, html, os, re, sys

try:
    import markdown
except ImportError:
    sys.exit("The 'markdown' package is required: pip install markdown  (add --break-system-packages if pip insists)")

SKIP = {"TRACKER.md", "USAGE.md"}
GROUPS = [("", "Playbook"), ("work-packages", "Work packages"), ("adr", "ADRs"), ("review", "Reviews"), ("decisions", "Decision cards")]

CSS = """
:root{--bg:#12151C;--surface:#1B212C;--surface-2:#212837;--border:#2A3140;--text:#E8EAED;--text-2:#A6AEBD;--text-3:#5A6272;--teal:#4FD1C5;--amber:#E8A33D;--coral:#E8735C;--blue:#7C9CE8;--violet:#B48EE8;
--sans:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;--mono:'IBM Plex Mono',SF Mono,Consolas,monospace}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F7F9;--surface:#fff;--surface-2:#EEF1F5;--border:#D9DEE6;--text:#1B2230;--text-2:#3E4756;--text-3:#8A93A3;--teal:#0E8F84;--amber:#B86E0A;--coral:#C4462C;--blue:#3A5BC7;--violet:#7A4FC7}}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.65}
.shell{display:flex;max-width:1320px;margin:0 auto}.side{width:260px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto;padding:28px 18px;border-right:1px solid var(--border);background:var(--bg)}
.side a{display:block;color:var(--text-2);text-decoration:none;font-size:13px;padding:5px 8px;border-radius:6px}.side a:hover{color:var(--teal);background:var(--surface)}
.side .lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-3);font-weight:600;margin:18px 0 6px}
.main{flex:1;min-width:0;padding:40px 48px 120px}.measure{max-width:880px}
h1{font-size:28px;line-height:1.25;margin-bottom:14px}h2{font-size:20px;margin:36px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}h3{font-size:16px;margin:24px 0 8px}
p{margin:10px 0;color:var(--text-2)}ul,ol{padding-left:24px;color:var(--text-2);margin:8px 0}li{margin:3px 0}strong{color:var(--text)}a{color:var(--teal)}
pre{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.55;margin:12px 0;position:relative;white-space:pre-wrap}
code{font-family:var(--mono);font-size:12.8px;background:var(--surface-2);padding:1px 5px;border-radius:4px}pre code{background:none;padding:0}
table{width:100%;border-collapse:collapse;font-size:13.3px;margin:12px 0;display:block;overflow-x:auto}th{text-align:left;background:var(--surface-2);color:var(--text-3);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:9px 11px;border-bottom:1px solid var(--border)}
td{padding:9px 11px;border-bottom:1px solid var(--border);color:var(--text-2);vertical-align:top}blockquote{border-left:3px solid var(--border);padding:4px 14px;color:var(--text-3);margin:10px 0}
.tag{font-family:var(--mono);font-size:11.5px;padding:1px 6px;border-radius:4px;border:1px solid;white-space:nowrap}
.t-src,.t-tested{color:var(--teal);border-color:var(--teal);background:rgba(79,209,197,.1)}.t-gap,.t-untested{color:var(--coral);border-color:var(--coral);background:rgba(232,115,92,.12)}
.t-drift{color:#F0C05A;border-color:#F0C05A;background:rgba(240,192,90,.1)}.t-planned{color:var(--blue);border-color:var(--blue);background:rgba(124,156,232,.1)}
.t-protected,.t-adr{color:var(--amber);border-color:var(--amber);background:rgba(232,163,61,.12)}.t-dc{color:var(--blue);border-color:var(--blue);background:rgba(124,156,232,.12);font-weight:600}
.t-risk{color:var(--violet);border-color:var(--violet);background:rgba(180,142,232,.12)}.t-stale{color:var(--violet);border-color:var(--violet)}.t-blocked{color:var(--coral);border-color:var(--coral);background:rgba(232,115,92,.18);font-weight:700}
.copy{position:absolute;top:8px;right:8px;font-size:11px;font-family:var(--sans);background:var(--surface-2);border:1px solid var(--border);color:var(--text-2);padding:4px 9px;border-radius:5px;cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 20px}.idx{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.idx a{display:block;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;text-decoration:none;color:var(--text)}.idx a:hover{border-color:var(--teal)}.idx .id{font-family:var(--mono);color:var(--teal);font-size:12px}
@media (max-width:900px){.side{display:none}.main{padding:24px 16px 100px}}
"""
TAG_RULES = [
    (re.compile(r"\[src:[^\]]*\]"), "t-src"), (re.compile(r"\[GAP(?:-\d+)?(?::[^\]]*)?\]"), "t-gap"),
    (re.compile(r"\[DRIFT(?:-\d+)?(?::[^\]]*)?\]"), "t-drift"), (re.compile(r"\[PLANNED(?::[^\]]*)?\]"), "t-planned"),
    (re.compile(r"\[PROTECTED\]"), "t-protected"), (re.compile(r"\[UNTESTED(?::[^\]]*)?\]"), "t-untested"),
    (re.compile(r"\[tested:[^\]]*\]"), "t-tested"), (re.compile(r"\[ADR-\d+[^\]]*\]"), "t-adr"),
    (re.compile(r"\[DC-\d+[^\]]*\]"), "t-dc"), (re.compile(r"\[RISK-\d+[^\]]*\]"), "t-risk"),
    (re.compile(r"\[STALE\]"), "t-stale"), (re.compile(r"\[BLOCKED[^\]]*\]"), "t-blocked"),
]
LEGEND = [("t-src", "[src]"), ("t-gap", "[GAP]"), ("t-drift", "[DRIFT]"), ("t-planned", "[PLANNED]"), ("t-tested", "[tested]"), ("t-untested", "[UNTESTED]"),
          ("t-adr", "[ADR]"), ("t-dc", "[DC]"), ("t-risk", "[RISK]"), ("t-stale", "[STALE]"), ("t-blocked", "[BLOCKED]")]


def highlight(h):
    parts = re.split(r"(<pre>.*?</pre>)", h, flags=re.S)
    for i, p in enumerate(parts):
        if p.startswith("<pre>"): continue
        for rx, cls in TAG_RULES: p = rx.sub(lambda m: f'<span class="tag {cls}">{m.group(0)}</span>', p)
        parts[i] = p
    return "".join(parts)


def page(title, nav, legend, body, rel):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet"><style>{CSS}</style></head>
<body><div class="shell"><nav class="side">{nav.replace('__R__', rel)}</nav><main class="main"><div class="measure"><div class="legend">{legend}</div>{body}</div></main></div>
<script>function cp(b){{var t=b.parentNode.innerText.replace(/^Copy\\n?/,'');navigator.clipboard.writeText(t).then(function(){{b.textContent='Copied';setTimeout(function(){{b.textContent='Copy'}},1500)}})}}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir"); ap.add_argument("--out", default=None); ap.add_argument("--title", default="Execution playbook")
    a = ap.parse_args(); src = a.dir.rstrip("/"); out = a.out or src; os.makedirs(out, exist_ok=True)

    files = {}  # group -> [md filenames]
    for sub, _ in GROUPS:
        d = os.path.join(src, sub) if sub else src
        if not os.path.isdir(d): continue
        files[sub] = sorted(f for f in os.listdir(d) if f.endswith(".md") and f not in SKIP and not f.startswith("_"))
    nav = [f'<a href="__R__index.html"><b>{html.escape(a.title)}</b></a>', '<a href="__R__TRACKER.html">Tracker</a><a href="__R__USAGE.html">Usage</a>']
    for sub, label in GROUPS:
        if files.get(sub):
            nav.append(f'<div class="lbl">{label}</div>')
            nav += [f'<a href="__R__{(sub + "/") if sub else ""}{f[:-3]}.html">{html.escape(f[:-3])}</a>' for f in files[sub]]
    nav_html = "".join(nav); legend = "".join(f'<span class="tag {c}">{t}</span>' for c, t in LEGEND)

    n = 0
    for sub, _ in GROUPS:
        if sub == "decisions": continue  # rendered by build_decision_card.py
        for f in files.get(sub, []):
            srcp = os.path.join(src, sub, f) if sub else os.path.join(src, f)
            text = open(srcp, encoding="utf-8").read()
            body = highlight(markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"]))
            body = body.replace("<pre>", '<pre><button class="copy" onclick="cp(this)">Copy</button>')
            od = os.path.join(out, sub) if sub else out; os.makedirs(od, exist_ok=True)
            open(os.path.join(od, f[:-3] + ".html"), "w", encoding="utf-8").write(page(f[:-3], nav_html, legend, body, "../" if sub else "")); n += 1

    cards = ""
    for sub, label in GROUPS:
        if not files.get(sub): continue
        cards += f"<h2>{label}</h2><div class='idx'>" + "".join(
            f'<a href="{(sub + "/") if sub else ""}{f[:-3]}.html"><div class="id">{html.escape(f[:-3])}</div><div>{html.escape(open(os.path.join(src, sub, f) if sub else os.path.join(src, f), encoding="utf-8").readline().lstrip("# ").strip())}</div></a>'
            for f in files[sub]) + "</div>"
    body = f"<h1>{html.escape(a.title)}</h1><p>Start at the <a href='TRACKER.html'>tracker</a>'s next action; the <a href='USAGE.html'>usage guide</a> explains tags and cards.</p>{cards}"
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page(a.title, nav_html, legend, body, "")); n += 1
    print(f"rendered {n} pages into {out}")


if __name__ == "__main__":
    main()
