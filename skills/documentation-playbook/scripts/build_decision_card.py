#!/usr/bin/env python3
"""
build_decision_card.py — render a Decision Card from JSON to decisions/DC-###.md (and .html),
and register its summary row in run-config.json so the tracker shows it.

Usage:
    python3 build_decision_card.py card.json --config run-config.json [--out DIR] [--format md|html|both]
    python3 build_decision_card.py card.json --config run-config.json --decide "B" --by "Mahdi" --rationale "..."
    python3 build_decision_card.py card.json --config run-config.json --auto-rule 4 --rationale "..."

Card schema (see assets/decision-card.example.json):
{
  "id": "DC-003",                      # omit to auto-number from the config register
  "title": "decision in one line",
  "wp": "WP-02",                       # "" for run-level cards (DC-000, Phase 5)
  "between": "Verify → WP-03 Design",
  "raised": "YYYY-MM-DD",
  "stops_run": false,                  # true for BLOCKED / irreversible / over-budget / protected drift / DC-000
  "reversible": true,
  "budget_impact": "none",
  "what_was_done": ["line [src: ...]", "..."],
  "evidence": {
    "gate": "PASS (attempt 2) — 48 tests, lint clean [src: logs/WP-02-gate-2.log]",
    "review": "PASS — F-01 (High, SECURITY) fixed in loop 1; F-02 (Low, MAINTAINABILITY) deferred",
    "gaps": ["GAP-004"], "adrs": ["ADR-002"], "drifts": []
  },
  "question": "one line",
  "options": [ {"key":"A","option":"...","consequence":"...","cost":"...","reversible":true,"risk":"..."} ],
  "recommendation": {"key":"A","reason":"..."},
  "default": {"key":"A","rule":4} | {"key":null,"rule":null,"note":"waits for a human"},
  "decision": {"key":"", "by":"", "rule":null, "date":"", "rationale":"", "followups":[]}
}
"""
import argparse, html, json, os, re, sys
from datetime import date

STATUS_OPEN, STATUS_DECIDED, STATUS_AUTO = "OPEN", "DECIDED", "AUTO-DECIDED"


def status_of(card):
    d = card.get("decision") or {}
    if not d.get("key"): return STATUS_OPEN
    return STATUS_AUTO if d.get("rule") else STATUS_DECIDED


def next_id(cfg):
    ids = [int(m.group(1)) for c in cfg.get("decision_cards", []) if (m := re.match(r"DC-(\d+)", c.get("id", "")))]
    return f"DC-{(max(ids) + 1 if ids else 0):03d}"


def md_card(c):
    d = c.get("decision") or {}; ev = c.get("evidence") or {}; st = status_of(c)
    o = []; w = o.append
    w(f"# {c['id']} — {c['title']}")
    w(f"Between: {c.get('between','')}   WP: {c.get('wp') or '— (run level)'}   Raised: {c.get('raised','')}   Status: {st}")
    w(f"Stops the run: {'yes' if c.get('stops_run') else 'no'}          Reversible: {'yes' if c.get('reversible', True) else 'no'}         Budget impact: {c.get('budget_impact','none')}\n")
    w("## What was done"); [w(f"- {x}") for x in c.get("what_was_done", [])] or w("- —"); w("")
    w("## Evidence")
    w(f"- Gate commands: {ev.get('gate','—')}"); w(f"- Reviewer verdict: {ev.get('review','—')}")
    w(f"- Open gaps raised here: {', '.join(ev.get('gaps', [])) or '—'}"); w(f"- ADRs needing a call: {', '.join(ev.get('adrs', [])) or '—'}")
    if ev.get("drifts"): w(f"- Drift: {', '.join(ev['drifts'])}")
    w(""); w("## Question"); w(c.get("question", "")); w("")
    w("## Options"); w("| | Option | Consequence | Cost | Reversible | Risk |\n|---|---|---|---|---|---|")
    for op in c.get("options", []):
        w(f"| {op.get('key','')} | {op.get('option','')} | {op.get('consequence','')} | {op.get('cost','')} | {'yes' if op.get('reversible', True) else 'no'} | {op.get('risk','')} |")
    w("")
    rec = c.get("recommendation") or {}
    w("## Recommendation"); w(f"{rec.get('key','—')} — {rec.get('reason','')}"); w("")
    df = c.get("default") or {}
    w("## Default if unanswered (automated mode)")
    w(f"{df['key']} by decision rule {df.get('rule','—')}" if df.get("key") else f"none: {df.get('note','waits for a human')}"); w("")
    w("## Decision")
    if st == STATUS_OPEN: w("_OPEN — answer with one line: `" + c["id"] + ": <option letter> — <rationale>`_")
    else:
        by = d.get("by") or (f"AUTO rule {d.get('rule')}" if d.get("rule") else "")
        w(f"{d.get('key')} · by {by} · on {d.get('date','')} · rationale: {d.get('rationale','')}")
        if d.get("followups"): w("Follow-ups: " + " · ".join(d["followups"]))
    return "\n".join(o) + "\n"


CSS = """
:root{--bg:#12151C;--surface:#1B212C;--surface-2:#212837;--border:#2A3140;--text:#E8EAED;--text-2:#A6AEBD;--text-3:#5A6272;--teal:#4FD1C5;--amber:#E8A33D;--coral:#E8735C;--blue:#7C9CE8;
--sans:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;--mono:'IBM Plex Mono',SF Mono,Consolas,monospace}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F7F9;--surface:#fff;--surface-2:#EEF1F5;--border:#D9DEE6;--text:#1B2230;--text-2:#3E4756;--text-3:#8A93A3;--teal:#0E8F84;--amber:#B86E0A;--coral:#C4462C;--blue:#3A5BC7}}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.6}
.wrap{max-width:900px;margin:0 auto;padding:32px 16px 96px}h1{font-size:24px;margin-bottom:8px}h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-3);margin:26px 0 8px}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 18px}.pill{font-family:var(--mono);font-size:11px;padding:3px 9px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-2)}
.pill.OPEN{color:var(--amber);border-color:var(--amber)}.pill.DECIDED{color:var(--teal);border-color:var(--teal)}.pill.AUTO-DECIDED{color:var(--blue);border-color:var(--blue)}.pill.stop{color:var(--coral);border-color:var(--coral);font-weight:600}
ul{padding-left:22px;color:var(--text-2)}li{margin:4px 0}p{color:var(--text-2)}
table{width:100%;border-collapse:collapse;font-size:13.3px;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}
th{text-align:left;background:var(--surface-2);color:var(--text-3);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:9px 11px}td{padding:9px 11px;border-top:1px solid var(--border);color:var(--text-2);vertical-align:top}
tr.rec td{background:rgba(79,209,197,.07)}.q{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:8px;padding:14px 16px;font-size:16px;color:var(--text)}
.dec{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--teal);border-radius:8px;padding:14px 16px}.dec.open{border-left-color:var(--amber)}
code{font-family:var(--mono);font-size:12.5px;background:var(--surface-2);padding:1px 5px;border-radius:4px}.tag{font-family:var(--mono);font-size:11.5px;padding:1px 6px;border-radius:4px;border:1px solid var(--teal);color:var(--teal)}
a{color:var(--teal)}.back{font-size:13px;margin-bottom:12px;display:block}
"""
TAG = re.compile(r"\[(src|GAP|DRIFT|ADR|DC|RISK|tested|UNTESTED|PLANNED|PROTECTED|STALE|BLOCKED)[^\]]*\]")


def esc(x): return html.escape(str(x if x is not None else ""))
def tagify(t): return TAG.sub(lambda m: f'<span class="tag">{m.group(0)}</span>', esc(t))


def html_card(c):
    d = c.get("decision") or {}; ev = c.get("evidence") or {}; st = status_of(c); rec = (c.get("recommendation") or {}).get("key")
    o = []; w = o.append
    w('<a class="back" href="../TRACKER.html">← Tracker</a>')
    w(f"<h1>{esc(c['id'])} — {esc(c['title'])}</h1>")
    w('<div class="meta">' + f'<span class="pill {st}">{st}</span>' + f'<span class="pill">{esc(c.get("between",""))}</span>' + f'<span class="pill">{esc(c.get("wp") or "run level")}</span>'
      + f'<span class="pill">raised {esc(c.get("raised",""))}</span>' + (f'<span class="pill stop">stops the run</span>' if c.get("stops_run") else "")
      + f'<span class="pill">{"reversible" if c.get("reversible", True) else "irreversible"}</span>' + f'<span class="pill">budget: {esc(c.get("budget_impact","none"))}</span></div>')
    w("<h2>What was done</h2><ul>" + "".join(f"<li>{tagify(x)}</li>" for x in c.get("what_was_done", [])) + "</ul>")
    w("<h2>Evidence</h2><ul>" + f"<li><b>Gate:</b> {tagify(ev.get('gate','—'))}</li><li><b>Review:</b> {tagify(ev.get('review','—'))}</li>"
      + f"<li><b>Gaps:</b> {tagify(', '.join(ev.get('gaps', [])) or '—')}</li><li><b>ADRs:</b> {tagify(', '.join(ev.get('adrs', [])) or '—')}</li>"
      + (f"<li><b>Drift:</b> {tagify(', '.join(ev['drifts']))}</li>" if ev.get("drifts") else "") + "</ul>")
    w(f'<h2>Question</h2><div class="q">{esc(c.get("question",""))}</div>')
    w("<h2>Options</h2><table><tr><th></th><th>Option</th><th>Consequence</th><th>Cost</th><th>Reversible</th><th>Risk</th></tr>")
    for op in c.get("options", []):
        w(f'<tr class="{"rec" if op.get("key") == rec else ""}"><td><b>{esc(op.get("key"))}</b></td><td>{tagify(op.get("option"))}</td><td>{tagify(op.get("consequence"))}</td><td>{esc(op.get("cost"))}</td><td>{"yes" if op.get("reversible", True) else "no"}</td><td>{tagify(op.get("risk"))}</td></tr>')
    w("</table>")
    r = c.get("recommendation") or {}; df = c.get("default") or {}
    w(f"<h2>Recommendation</h2><p><b>{esc(r.get('key','—'))}</b> — {tagify(r.get('reason',''))}</p>")
    w("<h2>Default if unanswered (automated mode)</h2><p>" + (f"<b>{esc(df['key'])}</b> by decision rule {esc(df.get('rule','—'))}" if df.get("key") else f"none: {esc(df.get('note','waits for a human'))}") + "</p>")
    w("<h2>Decision</h2>")
    if st == STATUS_OPEN:
        w(f'<div class="dec open">OPEN — answer with one line: <code>{esc(c["id"])}: &lt;option letter&gt; — &lt;rationale&gt;</code></div>')
    else:
        by = d.get("by") or (f"AUTO rule {d.get('rule')}" if d.get("rule") else "")
        w(f'<div class="dec"><b>{esc(d.get("key"))}</b> · by {esc(by)} · on {esc(d.get("date",""))}<br>{tagify(d.get("rationale",""))}' + (f"<br><span class='muted'>Follow-ups: {tagify(' · '.join(d['followups']))}</span>" if d.get("followups") else "") + "</div>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(c['id'])} — {esc(c['title'])}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet"><style>{CSS}</style></head><body><div class="wrap">{''.join(o)}</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card"); ap.add_argument("--config", required=True); ap.add_argument("--out", default=None)
    ap.add_argument("--format", choices=["md", "html", "both"], default=None)
    ap.add_argument("--decide", help="option key chosen by a human"); ap.add_argument("--by", default=""); ap.add_argument("--auto-rule", type=int, help="decision rule number that resolved it")
    ap.add_argument("--rationale", default=""); ap.add_argument("--followup", action="append", default=[])
    a = ap.parse_args()
    card = json.load(open(a.card, encoding="utf-8")); cfg = json.load(open(a.config, encoding="utf-8"))
    cfg.setdefault("decision_cards", [])
    if not card.get("id"): card["id"] = next_id(cfg)
    card.setdefault("raised", date.today().isoformat())
    if a.decide or a.auto_rule:
        card["decision"] = {"key": a.decide or (card.get("default") or {}).get("key"), "by": a.by, "rule": a.auto_rule,
                            "date": date.today().isoformat(), "rationale": a.rationale, "followups": a.followup}
        json.dump(card, open(a.card, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    fmt = a.format or cfg.get("format", "both"); out = a.out or os.path.join(cfg.get("output_dir", "_playbook/"), "decisions")
    os.makedirs(out, exist_ok=True); written = []
    if fmt in ("md", "both"):
        p = os.path.join(out, card["id"] + ".md"); open(p, "w", encoding="utf-8").write(md_card(card)); written.append(p)
    if fmt in ("html", "both"):
        p = os.path.join(out, card["id"] + ".html"); open(p, "w", encoding="utf-8").write(html_card(card)); written.append(p)
    d = card.get("decision") or {}
    row = {"id": card["id"], "title": card["title"], "wp": card.get("wp", ""), "between": card.get("between", ""), "status": status_of(card),
           "stops_run": bool(card.get("stops_run")), "decision": d.get("key") or "", "by": d.get("by") or "", "rule": d.get("rule"), "date": d.get("date") or card["raised"]}
    reg = cfg["decision_cards"]
    for i, r in enumerate(reg):
        if r.get("id") == card["id"]: reg[i] = row; break
    else: reg.append(row)
    if row["status"] == STATUS_OPEN and card.get("stops_run"):
        cfg["next_action"] = f"Answer {card['id']} — {card['title']} (run is stopped on it)."
    json.dump(cfg, open(a.config, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("wrote: " + ", ".join(written)); print(f"{card['id']} {row['status']} registered in {a.config}; regenerate the tracker with build_tracker.py")


if __name__ == "__main__":
    main()
