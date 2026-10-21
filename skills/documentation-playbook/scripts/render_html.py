#!/usr/bin/env python3
"""
render_html.py — render the Markdown corpus (core documents + lenses) into self-contained
HTML pages with a sidebar index, tag highlighting, and copy buttons on code blocks.
Markdown stays the authoring format; this is a view. Re-run after each phase.

Usage:
    python3 render_html.py DOCS_DIR [--out DIR] [--title "System name"]

- Renders every *.md in DOCS_DIR and DOCS_DIR/lenses (recursively one level) to .html beside it,
  or under --out mirroring the structure. Skips _playbook/ and files starting with "_".
- Writes index.html listing core documents (by NN_ prefix order) and lenses.
- Tags [src:…], [GAP…], [DRIFT…], [PLANNED…], [PROTECTED], [UNTESTED…], [tested:…], [STALE]
  are highlighted so they can be scanned.
Requires the "markdown" package:  pip install markdown
"""
import argparse, html, os, re, sys

try:
    import markdown
except ImportError:
    sys.exit("The 'markdown' package is required: pip install markdown  (add --break-system-packages if pip insists)")

CSS = """
:root{--bg:#12151C;--surface:#1B212C;--surface-2:#212837;--border:#2A3140;--text:#E8EAED;--text-2:#A6AEBD;--text-3:#5A6272;--teal:#4FD1C5;--amber:#E8A33D;--coral:#E8735C;--blue:#7C9CE8;--violet:#B48EE8;
--sans:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;--mono:'IBM Plex Mono',SF Mono,Consolas,monospace}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F7F9;--surface:#fff;--surface-2:#EEF1F5;--border:#D9DEE6;--text:#1B2230;--text-2:#3E4756;--text-3:#8A93A3;--teal:#0E8F84;--amber:#B86E0A;--coral:#C4462C;--blue:#3A5BC7;--violet:#7A4FC7}}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.65}
.shell{display:flex;max-width:1320px;margin:0 auto}.side{width:260px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto;padding:28px 18px;border-right:1px solid var(--border);background:var(--bg)}
.side a{display:block;color:var(--text-2);text-decoration:none;font-size:13px;padding:5px 8px;border-radius:6px}.side a:hover,.side a.on{color:var(--teal);background:var(--surface)}
.side .lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-3);font-weight:600;margin:18px 0 6px}
.main{flex:1;min-width:0;padding:40px 48px 120px}.measure{max-width:880px}
h1{font-size:28px;line-height:1.25;margin-bottom:14px}h2{font-size:20px;margin:36px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}h3{font-size:16px;margin:24px 0 8px}h4{font-size:14.5px;margin:18px 0 6px}
p{margin:10px 0;color:var(--text-2)}ul,ol{padding-left:24px;color:var(--text-2);margin:8px 0}li{margin:3px 0}strong{color:var(--text)}a{color:var(--teal)}
pre{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.55;margin:12px 0;position:relative;white-space:pre-wrap}
code{font-family:var(--mono);font-size:12.8px;background:var(--surface-2);padding:1px 5px;border-radius:4px}pre code{background:none;padding:0}
table{width:100%;border-collapse:collapse;font-size:13.3px;margin:12px 0;display:block;overflow-x:auto}th{text-align:left;background:var(--surface-2);color:var(--text-3);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:9px 11px;border-bottom:1px solid var(--border)}
td{padding:9px 11px;border-bottom:1px solid var(--border);color:var(--text-2);vertical-align:top}blockquote{border-left:3px solid var(--border);padding:4px 14px;color:var(--text-3);margin:10px 0}
.hdr{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 16px;font-family:var(--mono);font-size:12.3px;color:var(--text-2);margin:0 0 20px;white-space:pre-wrap}
.tag{font-family:var(--mono);font-size:11.5px;padding:1px 6px;border-radius:4px;border:1px solid;white-space:nowrap}
.t-src{color:var(--teal);border-color:var(--teal);background:rgba(79,209,197,.1)}.t-gap{color:var(--coral);border-color:var(--coral);background:rgba(232,115,92,.12)}
.t-drift{color:#F0C05A;border-color:#F0C05A;background:rgba(240,192,90,.1)}.t-planned{color:var(--blue);border-color:var(--blue);background:rgba(124,156,232,.1)}
.t-protected{color:var(--amber);border-color:var(--amber);background:rgba(232,163,61,.12);font-weight:600}.t-untested{color:var(--coral);border-color:var(--coral);background:rgba(232,115,92,.12)}
.t-tested{color:var(--teal);border-color:var(--teal);background:rgba(79,209,197,.1)}.t-stale{color:var(--violet);border-color:var(--violet);background:rgba(180,142,232,.12)}.t-tbd{color:var(--text-3);border-color:var(--text-3)}
.copy{position:absolute;top:8px;right:8px;font-size:11px;font-family:var(--sans);background:var(--surface-2);border:1px solid var(--border);color:var(--text-2);padding:4px 9px;border-radius:5px;cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 20px}.idx{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.idx a{display:block;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;text-decoration:none;color:var(--text)}.idx a:hover{border-color:var(--teal)}.idx .id{font-family:var(--mono);color:var(--teal);font-size:12px}.idx .m{color:var(--text-3);font-size:12px;margin-top:4px}
@media (max-width:900px){.side{display:none}.main{padding:24px 16px 100px}}
"""

TAG_RULES = [
    (re.compile(r"\[src:[^\]]*\]"), "t-src"),
    (re.compile(r"\[GAP(?:-\d+)?(?::[^\]]*)?\]"), "t-gap"),
    (re.compile(r"\[DRIFT(?:-\d+)?(?::[^\]]*)?\]"), "t-drift"),
    (re.compile(r"\[PLANNED(?::[^\]]*)?\]"), "t-planned"),
    (re.compile(r"\[PROTECTED\]"), "t-protected"),
    (re.compile(r"\[UNTESTED(?::[^\]]*)?\]"), "t-untested"),
    (re.compile(r"\[tested:[^\]]*\]"), "t-tested"),
    (re.compile(r"\[STALE\]"), "t-stale"),
    (re.compile(r"\[rule: ?TBD\]"), "t-tbd"),
]
LEGEND = [("t-src", "[src]"), ("t-gap", "[GAP]"), ("t-drift", "[DRIFT]"), ("t-planned", "[PLANNED]"),
          ("t-protected", "[PROTECTED]"), ("t-untested", "[UNTESTED]"), ("t-tested", "[tested]"), ("t-stale", "[STALE]")]


def highlight_tags(h):
    # Only outside <pre> blocks; code blocks keep raw text so copy buttons copy the exact prompt.
    parts = re.split(r"(<pre>.*?</pre>)", h, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("<pre>"):
            continue
        for rx, cls in TAG_RULES:
            part = rx.sub(lambda m: f'<span class="tag {cls}">{m.group(0)}</span>', part)
        parts[i] = part
    return "".join(parts)


def split_header(md_text):
    """Pull the playbook header block (System:/Scope:/Version:/Authority:/Maturity:) out of the top."""
    lines = md_text.splitlines()
    if not lines or not lines[0].startswith("# "):
        return None, None, md_text
    title = lines[0][2:].strip()
    hdr, rest, i = [], [], 1
    while i < len(lines) and re.match(r"^(System|Scope|Version|Authority|Maturity[^:]*|Lens):", lines[i]):
        hdr.append(lines[i]); i += 1
    return title, "\n".join(hdr), "\n".join(lines[i:])


MERMAID_JS = '<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script><script>mermaid.initialize({startOnLoad:true,securityLevel:"loose",theme:matchMedia("(prefers-color-scheme: dark)").matches?"dark":"neutral"});</script>'


def mermaid_blocks(h):
    """Turn ```mermaid fenced blocks (rendered by the markdown lib as <pre><code class="language-mermaid">)
    into <pre class="mermaid"> so Mermaid draws them as static SVG."""
    def repl(m):
        src = html.unescape(m.group(1))
        return f'<pre class="mermaid">{html.escape(src)}</pre>'
    return re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', repl, h, flags=re.S)


def render_doc(md_path, nav_html, legend_html, rel_root):
    text = open(md_path, encoding="utf-8").read()
    title, hdr, body_md = split_header(text)
    body = markdown.markdown(body_md, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    body = mermaid_blocks(body)
    body = highlight_tags(body)
    body = re.sub(r"<pre>(?!<button)", '<pre><button class="copy" onclick="cp(this)">Copy</button>', body)
    t = html.escape(title or os.path.basename(md_path))
    hdr_html = f'<div class="hdr">{highlight_tags(html.escape(hdr))}</div>' if hdr else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet"><style>{CSS}</style></head>
<body><div class="shell"><nav class="side">{nav_html.replace('__ROOT__', rel_root)}</nav><main class="main"><div class="measure">
<h1>{t}</h1>{hdr_html}<div class="legend">{legend_html}</div>{body}</div></main></div>
{MERMAID_JS if 'class="mermaid"' in body else ''}
<script>function cp(b){{var t=b.parentNode.innerText.replace(/^Copy\\n?/,'');navigator.clipboard.writeText(t).then(function(){{b.textContent='Copied';setTimeout(function(){{b.textContent='Copy'}},1500)}})}}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default="Documentation corpus")
    a = ap.parse_args()
    src = a.docs_dir.rstrip("/")
    out = a.out or src
    os.makedirs(out, exist_ok=True)

    core = sorted(f for f in os.listdir(src) if f.endswith(".md") and not f.startswith("_") and re.match(r"^\d\d_", f))
    # TRACKER.md / USAGE.md have their own richer renderer (build_tracker.py) — never overwrite those pages here.
    OWN_RENDERER = {"TRACKER.md", "USAGE.md"}
    extra = sorted(f for f in os.listdir(src) if f.endswith(".md") and not f.startswith("_") and f not in core and f not in OWN_RENDERER)
    lens_dir = os.path.join(src, "lenses")
    lenses = sorted(f for f in os.listdir(lens_dir) if f.endswith(".md")) if os.path.isdir(lens_dir) else []

    def label(f):
        m = re.match(r"^\d\d_([A-Z]+)\.md$", f)
        return m.group(1) if m else f[:-3]

    nav = [f'<a href="__ROOT__index.html"><b>{html.escape(a.title)}</b></a>', '<div class="lbl">Core corpus</div>']
    nav += [f'<a href="__ROOT__{f[:-3]}.html">{label(f)}</a>' for f in core]
    if lenses:
        nav.append('<div class="lbl">Lenses</div>')
        nav += [f'<a href="__ROOT__lenses/{f[:-3]}.html">{f[:-3].replace("LENS-", "")}</a>' for f in lenses]
    if extra:
        nav.append('<div class="lbl">Other</div>')
        nav += [f'<a href="__ROOT__{f[:-3]}.html">{f[:-3]}</a>' for f in extra]
    nav_html = "".join(nav)
    legend_html = "".join(f'<span class="tag {c}">{t}</span>' for c, t in LEGEND)

    written = []
    for f in core + extra:
        p = os.path.join(out, f[:-3] + ".html")
        open(p, "w", encoding="utf-8").write(render_doc(os.path.join(src, f), nav_html, legend_html, ""))
        written.append(p)
    if lenses:
        os.makedirs(os.path.join(out, "lenses"), exist_ok=True)
        for f in lenses:
            p = os.path.join(out, "lenses", f[:-3] + ".html")
            open(p, "w", encoding="utf-8").write(render_doc(os.path.join(lens_dir, f), nav_html, legend_html, "../"))
            written.append(p)

    def maturity(f, d):
        txt = open(os.path.join(d, f), encoding="utf-8").read()
        m = re.search(r"^Maturity[^:]*:\s*(.+)$", txt, re.M)
        return html.escape(m.group(1)) if m else ""

    cards = "".join(f'<a href="{f[:-3]}.html"><div class="id">{label(f)}</div><div>{html.escape(open(os.path.join(src, f), encoding="utf-8").readline()[2:].strip())}</div><div class="m">{maturity(f, src)}</div></a>' for f in core)
    lens_cards = "".join(f'<a href="lenses/{f[:-3]}.html"><div class="id">{f[:-3]}</div><div class="m">{maturity(f, lens_dir)}</div></a>' for f in lenses)
    idx = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(a.title)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet"><style>{CSS}</style></head>
<body><div class="shell"><nav class="side">{nav_html.replace('__ROOT__', '')}</nav><main class="main"><div class="measure"><h1>{html.escape(a.title)}</h1>
<p>Ground-truth corpus. Start from your lens; follow citations into the core.</p><div class="legend">{legend_html}</div>
<h2>Core documents</h2><div class="idx">{cards}</div>{'<h2>Lenses</h2><div class="idx">'+lens_cards+'</div>' if lenses else ''}
<p style="margin-top:28px"><a href="TRACKER.html">Execution tracker</a> · <a href="USAGE.html">Usage guide</a></p></div></main></div></body></html>"""
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(idx)
    written.append(os.path.join(out, "index.html"))
    print(f"rendered {len(written)} pages into {out}")


if __name__ == "__main__":
    main()
