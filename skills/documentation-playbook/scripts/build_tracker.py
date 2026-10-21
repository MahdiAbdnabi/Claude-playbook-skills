#!/usr/bin/env python3
"""
build_tracker.py — render the playbook execution tracker and the short usage guide
from a run-config JSON. The config is the source of truth; the tracker files are views.
Re-run after every phase/checkpoint; outputs are overwritten.

Usage:
    python3 build_tracker.py run-config.json [--out DIR] [--format md|html|both]

Config schema (all keys optional except "system"; see assets/run-config.example.json):
{
  "system": "Name resolved in Phase 0 (or working name + [GAP-001])",
  "target": "how the code is reached",
  "summary": "owner-provided summary, context not evidence",
  "mode": "automated" | "monitored",
  "format": "md" | "html" | "both",
  "output_dir": "docs/",
  "started": "YYYY-MM-DD",
  "corpus_ref": "git sha / snapshot date the corpus describes",
  "cost_profile": "very-low" | "recommended" | "rich",                # default recommended
  "audit_depth": "none" | "low" | "medium" | "high",                  # Phase 5 effort; default low for 10min, medium otherwise
  "budget_calls": {"0":16,"1":25,"2":18,"3":12,"4":10,"5":12,"5re":8,"6":8},   # per-phase tool-call caps; defaults by depth
  "budget_tokens_continue": 150000,                                   # fix continues the extractor only under this conversation size
  "decision_cards": [ {"id","title","wp","between","status","stops_run","decision","by","rule","date"} ],
  "checks": [ {"check":3,"batch","date","citations_total","resolved","unresolved","hedges","untraced","blocking":false} ],
  "depth": "full" | "30min" | "10min",                                # default full
  "content": "docs+diagrams" | "docs" | "diagrams",                   # default docs+diagrams
  "diagram_style": "static" | "interactive" | "none",                 # default static; interactive needs HTML
  "diagram_depth": "hld" | "design" | "tracking",                     # default design
  "lenses": [ {"id","audience","entry_points":[...],"concerns"} ],   # defaults added if absent
  "models": { "0": {"tier":"mid","effort":"high","critical":false}, ... },  # RECOMMENDED per phase; defaults added if absent
                                                                     # tiers: small|mid|strong|top; efforts: low|medium|high|xhigh|max
                                                                     # the resolved (profile-adjusted) tier/effort is computed, not stored
  "seed_invariants": [ "..." ],
  "phase_status": { "0": "done", "5": "pending", "6": "pending" },   # cross-batch phases
  "batches": [ {"name","modules":[...],"pilot":true,
                "phases": {"1":"done","2":"in_progress","3":"pending","4":"pending"}} ],
  "gaps":   [ {"id","desc","severity","found_in","blocks","question","answered"} ],
  "drifts": [ {"id","desc","side_a","side_b","protected":bool,"decision"} ],
  "decisions": [ {"date","decision","by"} ],
  "citation_samples": [ {"date","scope","sampled","hits","misses":[...]} ],
  "sessions": [ {"date","phase","batch","model","calls":17,"cap":25,"tokens":41000,"attempt":1,"scope":"full|scoped","fix":"continued|fresh","notes"} ],
  "delta_rounds": [ {"date","from_ref","to_ref","stale","cleared","updated","notes"} ],
  "next_action": "the exact next prompt to run"
}
Status values: pending | in_progress | done | blocked | skipped
"""
import argparse, html, json, os, sys
from datetime import date

PHASES = [
    ("0", "Recon & pilot selection", "per run"),
    ("1", "Core extraction", "per batch"),
    ("2", "BRI, invariants & TST", "per batch"),
    ("3", "Flow / UX / Ops closeout", "per batch"),
    ("4", "Role lenses", "per batch"),
    ("5", "Evidence audit", "pilot, then all"),
    ("6", "KB packaging", "per run"),
]
BATCH_PHASES = ["1", "2", "3", "4"]
RUN_PHASES = ["0", "5", "6"]

DEFAULT_LENSES = [
    {"id": "ARCH", "audience": "Architect", "entry_points": ["ARC", "MOD", "INT", "DEP", "XCC"],
     "concerns": "boundaries, seams, topology, contracts, dependency risk"},
    {"id": "DEV", "audience": "Developer", "entry_points": ["MOD", "CNV", "DAT", "API", "UXF", "BRI", "TST"],
     "concerns": "where to change X, conventions, cited rules, test cover before touching [PROTECTED]"},
    {"id": "QA", "audience": "Tester", "entry_points": ["FLW", "BRI", "TST", "UXF", "GAP log"],
     "concerns": "decision points & expected outcomes, tested vs untested, flagged edge cases"},
    {"id": "BA", "audience": "Business analyst", "entry_points": ["FLW", "BRI", "UXF", "IDX glossary"],
     "concerns": "what the system does for the business, in plain language"},
]
DEFAULT_MODELS = {
    "0": {"tier": "mid", "effort": "high", "critical": False},
    "1": {"tier": "mid", "effort": "high", "critical": False, "note": "small for DEP/DTO enumeration"},
    "2": {"tier": "strong", "effort": "xhigh", "critical": True},
    "3": {"tier": "mid", "effort": "high", "critical": False},
    "4": {"tier": "small", "effort": "medium", "critical": False},
    "5": {"tier": "strong", "effort": "xhigh", "critical": True},
    "6": {"tier": "mid", "effort": "high", "critical": False},
    "5re": {"tier": "mid", "effort": "high", "critical": False, "note": "scoped re-audit; escalates to '5' on a trigger"},
}
AUDIT = {"none": "None — doc_check only, no independent audit", "low": "Low — mechanical citation sample (~5–10k/audit)", "medium": "Medium — auditor pack + 5 falsifications (~15–40k/audit)", "high": "High — full corpus + repo (~80–300k/audit)"}
CALL_BUDGETS = {"10min": {"0": 12, "1": 15, "2": 12, "3": 0, "4": 6, "5": 8, "5re": 5, "6": 0},
                "30min": {"0": 16, "1": 25, "2": 18, "3": 12, "4": 10, "5": 12, "5re": 8, "6": 8},
                "full": {"0": 20, "1": 40, "2": 25, "3": 18, "4": 12, "5": 20, "5re": 10, "6": 10}}
TIERS = ["small", "mid", "strong", "top"]
TIER_NAMES = {"small": "haiku", "mid": "sonnet", "strong": "opus", "top": "fable"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
PROFILES = {"very-low": "Very Low Budget", "recommended": "Recommended", "rich": "I Am Too Rich"}
DEPTHS = {"full": "Full documentation", "30min": "30-minute version", "10min": "10-minute version"}
CONTENTS = {"docs+diagrams": "Docs + diagrams", "docs": "Docs only", "diagrams": "Diagrams only"}
DSTYLES = {"static": "Static (Mermaid)", "interactive": "Interactive (HTML)", "none": "None"}
DDEPTHS = {"hld": "High-level design (D1–D3)", "design": "Design (D1–D7)", "tracking": "Full tracking (D1–D10)"}
STATUS_MARK = {"pending": "☐", "in_progress": "◐", "done": "☑", "blocked": "⛔", "skipped": "–"}


def output_profile(cfg):
    """One-line statement of the output profile, plus the phases it skips."""
    d, c, s, dd = cfg["depth"], cfg["content"], cfg["diagram_style"], cfg["diagram_depth"]
    parts = [DEPTHS[d], CONTENTS[c]]
    if c != "docs" and s != "none":
        parts.append(f"{DSTYLES[s]} at {DDEPTHS[dd]}")
    skips = {"full": [], "30min": [], "10min": ["3", "6"]}[d]
    return " · ".join(parts), skips


def resolve_models(cfg):
    """Apply the cost profile to the recommended per-phase tier/effort. Rules: cost-and-orchestration.md §2."""
    prof = cfg.get("cost_profile", "recommended")
    out = {}
    for pid, m in cfg["models"].items():
        t = TIERS.index(m["tier"]) if m["tier"] in TIERS else 1
        e = EFFORTS.index(m["effort"]) if m["effort"] in EFFORTS else 2
        crit = bool(m.get("critical"))
        if prof == "very-low":
            t = max(t - 2, TIERS.index("mid") if crit else 0)
            e = max(e - 1, EFFORTS.index("medium") if crit else 0)
        elif prof == "rich":
            if t < len(TIERS) - 1: t += 1
            else: e = min(e + 1, len(EFFORTS) - 1)
        out[pid] = {"tier": TIERS[t], "model": TIER_NAMES[TIERS[t]], "effort": EFFORTS[e]}
    return out


def used_models(cfg):
    """Phase → set of 'model / effort' strings actually recorded in the session log."""
    used = {}
    for s in cfg.get("sessions", []):
        p = str(s.get("phase", "")).strip()
        if p and s.get("model"):
            used.setdefault(p, [])
            if s["model"] not in used[p]: used[p].append(s["model"])
    return used


def load(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if "system" not in cfg:
        sys.exit("config needs at least a \"system\" name")
    cfg.setdefault("mode", "monitored")
    cfg.setdefault("format", "both")
    cfg.setdefault("output_dir", "docs/")
    cfg.setdefault("started", date.today().isoformat())
    cfg.setdefault("lenses", [])
    ids = {l["id"] for l in cfg["lenses"]}
    cfg["lenses"] = DEFAULT_LENSES + [l for l in cfg["lenses"] if l["id"] not in {d["id"] for d in DEFAULT_LENSES}] \
        if not ids & {d["id"] for d in DEFAULT_LENSES} else cfg["lenses"]
    models = {k: dict(v) for k, v in DEFAULT_MODELS.items()}
    for k, v in cfg.get("models", {}).items():
        models.setdefault(k, {}).update(v)
    cfg["models"] = models
    cfg.setdefault("cost_profile", "recommended")
    if cfg["cost_profile"] not in PROFILES:
        sys.exit(f"cost_profile must be one of {list(PROFILES)}")
    cfg["resolved_models"] = resolve_models(cfg)
    cfg.setdefault("depth", "full"); cfg.setdefault("content", "docs+diagrams")
    cfg.setdefault("diagram_style", "static"); cfg.setdefault("diagram_depth", "design")
    for k, allowed in (("depth", DEPTHS), ("content", CONTENTS), ("diagram_style", DSTYLES), ("diagram_depth", DDEPTHS)):
        if cfg[k] not in allowed: sys.exit(f"{k} must be one of {list(allowed)}")
    if cfg["content"] == "docs": cfg["diagram_style"] = "none"
    if cfg["content"] == "diagrams" and cfg["diagram_style"] == "none": sys.exit("content=diagrams needs diagram_style static or interactive")
    if cfg["diagram_style"] == "interactive" and cfg["format"] == "md":
        print("note: interactive diagrams need HTML — format switched to both", file=sys.stderr); cfg["format"] = "both"
    cfg["skipped_phases"] = output_profile(cfg)[1]
    cfg.setdefault("audit_depth", "low" if cfg["depth"] == "10min" else "medium")
    if cfg["audit_depth"] not in AUDIT: sys.exit(f"audit_depth must be one of {list(AUDIT)}")
    bc = dict(CALL_BUDGETS[cfg["depth"]]);
    if cfg["audit_depth"] == "high": bc["5"] += 10
    bc.update(cfg.get("budget_calls", {})); cfg["budget_calls"] = bc
    cfg.setdefault("decision_cards", []); cfg.setdefault("checks", [])
    cfg.setdefault("seed_invariants", [])
    ps = {p: "pending" for p in RUN_PHASES}; ps.update(cfg.get("phase_status", {})); cfg["phase_status"] = ps
    for p in cfg["skipped_phases"]:
        if p in RUN_PHASES and ps.get(p) != "done": ps[p] = "skipped"
    for b in cfg.setdefault("batches", []):
        b.setdefault("modules", []); b.setdefault("pilot", False)
        bp = {p: "pending" for p in BATCH_PHASES}; bp.update(b.get("phases", {})); b["phases"] = bp
        for p in cfg["skipped_phases"]:
            if p in BATCH_PHASES and bp[p] != "done": bp[p] = "skipped"
    for k in ("gaps", "drifts", "decisions", "citation_samples", "sessions", "delta_rounds"):
        cfg.setdefault(k, [])
    cfg.setdefault("next_action", "Run Phase 0 (recon & pilot selection).")
    return cfg


def summarise(cfg):
    gaps = cfg["gaps"]
    open_gaps = [g for g in gaps if not g.get("answered")]
    s = {
        "batches": len(cfg["batches"]),
        "batches_done": sum(1 for b in cfg["batches"] if all(v in ("done", "skipped") for v in b["phases"].values())),
        "open_blocking": sum(1 for g in open_gaps if g.get("severity") == "Blocking"),
        "open_high": sum(1 for g in open_gaps if g.get("severity") == "High"),
        "open_low": sum(1 for g in open_gaps if g.get("severity") == "Low"),
        "answered": len(gaps) - len(open_gaps),
        "drifts_open": sum(1 for d in cfg["drifts"] if not d.get("decision")),
        "drifts_protected": sum(1 for d in cfg["drifts"] if d.get("protected")),
    }
    sess = cfg.get("sessions", [])
    s["calls_total"] = sum(x.get("calls") or 0 for x in sess)
    s["cap_hits"] = sum(1 for x in sess if x.get("calls") is not None and x.get("cap") and x["calls"] >= x["cap"])
    audits = [x for x in sess if str(x.get("phase")) == "5" and x.get("tokens")]
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
    s["audit_first_avg"] = avg([x["tokens"] for x in audits if (x.get("attempt") or 1) == 1]); s["audit_re_avg"] = avg([x["tokens"] for x in audits if (x.get("attempt") or 1) > 1])
    s["re_scoped"] = sum(1 for x in audits if (x.get("attempt") or 1) > 1 and x.get("scope") == "scoped"); s["re_full"] = sum(1 for x in audits if (x.get("attempt") or 1) > 1 and x.get("scope") == "full")
    s["cards_open"] = sum(1 for c in cfg["decision_cards"] if c.get("status") == "OPEN"); s["cards_auto"] = sum(1 for c in cfg["decision_cards"] if c.get("status") == "AUTO-DECIDED")
    chk = cfg["checks"][-1] if cfg["checks"] else None
    s["last_check"] = f"check {chk['check']}: {chk.get('resolved',0)}/{chk.get('citations_total',0)} resolved · {chk.get('unresolved',0)} unresolved · {chk.get('hedges',0)} hedges · {chk.get('untraced',0)} untraced" if chk else "not run yet"
    cs = cfg["citation_samples"]
    if cs:
        last = cs[-1]
        s["hit_rate"] = f'{last.get("hits", 0)}/{last.get("sampled", 0)} ({last.get("scope", "")}, {last.get("date", "")})'
    else:
        s["hit_rate"] = "not run yet"
    return s


# ---------------------------------------------------------------- Markdown
def md_tracker(cfg):
    s = summarise(cfg)
    mode_label = "Fully Automated" if cfg["mode"] == "automated" else "User Monitored"
    out = []
    w = out.append
    w(f"# Playbook Execution Tracker — {cfg['system']}")
    w("")
    w(f"> **Next action:** {cfg['next_action']}")
    w("")
    w("## Run configuration")
    w("")
    w("| Key | Value |\n|---|---|")
    w(f"| Mode | {mode_label} |")
    w(f"| Output format | {cfg['format'].upper()} |")
    w(f"| Output location | `{cfg['output_dir']}` |")
    w(f"| Target access | {cfg.get('target', '—')} |")
    w(f"| Started | {cfg['started']} |")
    w(f"| Corpus describes | {cfg.get('corpus_ref', '— (record the commit/snapshot in Phase 0)')} |")
    w(f"| Cost profile | {PROFILES[cfg['cost_profile']]} |")
    op, skips = output_profile(cfg)
    w(f"| Output profile | {op}{' — skips Phase ' + ', '.join(skips) if skips else ''} |")
    w(f"| Audit effort | {AUDIT[cfg['audit_depth']]} |")
    w(f"| Call budget per phase | " + " · ".join(f"{k} {v}" for k, v in cfg['budget_calls'].items() if v) + " (cap hit → clean handoff + Decision Card) |")
    w(f"| Active lenses | {', '.join(l['id'] for l in cfg['lenses'])} |")
    w(f"| Seed [PROTECTED] invariants | {len(cfg['seed_invariants']) or 'none — Phase 2 proposes candidates'} |")
    w("")
    if cfg.get("summary"):
        w("**Owner summary (context, not evidence):** " + cfg["summary"])
        w("")
    if cfg["seed_invariants"]:
        w("**Seed invariants**")
        w("")
        for i, inv in enumerate(cfg["seed_invariants"], 1):
            w(f"{i}. [PROTECTED] {inv}")
        w("")
    w("## At a glance")
    w("")
    w(f"- Batches: {s['batches_done']}/{s['batches']} complete through Phase 4")
    w(f"- Open gaps: {s['open_blocking']} Blocking · {s['open_high']} High · {s['open_low']} Low · {s['answered']} answered")
    w(f"- Drift: {s['drifts_open']} undecided ({s['drifts_protected']} touching [PROTECTED])")
    w(f"- Last citation-sample hit rate: {s['hit_rate']}")
    w(f"- Last doc_check: {s['last_check']}")
    w(f"- Tool calls logged: {s['calls_total']} · cap hits: {s['cap_hits']} · Decision cards open: {s['cards_open']} (auto-decided {s['cards_auto']})")
    if s["audit_first_avg"] or s["audit_re_avg"]:
        w(f"- Audit cost: first audits avg {s['audit_first_avg']:,} tok · re-audits avg {s['audit_re_avg']:,} tok ({s['re_scoped']} scoped / {s['re_full']} full)")
    w("")
    w("## Phase plan, model & effort")
    w("")
    w(f"Cost profile **{PROFILES[cfg['cost_profile']]}** — the orchestrator launches each phase's agent with the *resolved* model/effort; *used* comes from the session log.")
    w("")
    w("| Phase | Scope | Recommended | Resolved (this profile) | Used | Status |\n|---|---|---|---|---|---|")
    used = used_models(cfg)
    for pid, name, scope in PHASES:
        m = cfg["models"][pid]; r = cfg["resolved_models"][pid]
        if pid in RUN_PHASES:
            st = cfg["phase_status"][pid]
        else:
            vals = [b["phases"][pid] for b in cfg["batches"]]
            st = "pending" if not vals else ("skipped" if all(v == "skipped" for v in vals) else "done" if all(v in ("done", "skipped") for v in vals) else
                                              "in_progress" if any(v not in ("pending", "skipped") for v in vals) else "pending")
        crit = " ⚑" if m.get("critical") else ""
        note = f" ({m['note']})" if m.get("note") else ""
        w(f"| {pid} — {name}{crit} | {scope} | {m['tier']} / {m['effort']}{note} | **{r['model']}** / {r['effort']} | {', '.join(used.get(pid, [])) or '—'} | {STATUS_MARK.get(st, st)} {st} |")
    w("")
    mr = cfg["models"]["5re"]; rr = cfg["resolved_models"]["5re"]
    w(f"| 5 — scoped re-audit | per failed audit | {mr['tier']} / {mr['effort']} ({mr.get('note','')}) | **{rr['model']}** / {rr['effort']} | {', '.join(used.get('5re', [])) or '—'} | — |")
    w("")
    w("⚑ = critical phase: floors at sonnet/medium under Very Low Budget; first to move up under I Am Too Rich.")
    w("")
    w("## Batch × phase matrix")
    w("")
    if not cfg["batches"]:
        w("_Batch plan not yet produced — Phase 0 fills this in._")
    else:
        w("| Batch | Modules | Ph 1 | Ph 2 | Ph 3 | Ph 4 |\n|---|---|---|---|---|---|")
        for b in cfg["batches"]:
            name = ("★ " if b["pilot"] else "") + b["name"]
            cells = " | ".join(f"{STATUS_MARK.get(b['phases'][p], '')} {b['phases'][p]}" for p in BATCH_PHASES)
            w(f"| {name} | {', '.join(b['modules']) or '—'} | {cells} |")
        w("")
        w("★ = pilot batch (runs Phases 1–5 before any other batch starts).")
    w("")
    w("## Decision cards")
    w("")
    if not cfg["decision_cards"]: w("_None raised yet. DC-000 approves the batch plan at the end of Phase 0._")
    else:
        w("| Id | Title | Between | Status | Stops run | Decision | By / rule | Date |\n|---|---|---|---|---|---|---|---|")
        for c in cfg["decision_cards"]:
            by = c.get("by") or (f"AUTO rule {c['rule']}" if c.get("rule") else "—")
            w(f"| {c.get('id','')} | {c.get('title','')} | {c.get('between','')} | {c.get('status','')} | {'yes' if c.get('stops_run') else 'no'} | {c.get('decision') or '—'} | {by} | {c.get('date','')} |")
    w("")
    w("## doc_check history")
    w("")
    if not cfg["checks"]: w("_No checks recorded. Run `scripts/doc_check.py` at the end of every extraction phase._")
    else:
        w("| # | Batch | Date | Citations | Resolved | Unresolved | Hedges | Untraced | Status |\n|---|---|---|---|---|---|---|---|---|")
        for c in cfg["checks"]:
            w(f"| {c.get('check','')} | {c.get('batch','') or '—'} | {c.get('date','')} | {c.get('citations_total','')} | {c.get('resolved','')} | {c.get('unresolved','')} | {c.get('hedges','')} | {c.get('untraced','')} | {'⛔ blocking' if c.get('blocking') else '☑ clean'} |")
    w("")
    w("## GAP log")
    w("")
    if not cfg["gaps"]:
        w("_No gaps logged yet._")
    else:
        w("| Id | Severity | Description | Found in | Blocks | Question | Answered |\n|---|---|---|---|---|---|---|")
        order = {"Blocking": 0, "High": 1, "Low": 2}
        for g in sorted(cfg["gaps"], key=lambda g: (bool(g.get("answered")), order.get(g.get("severity"), 3), g.get("id", ""))):
            w(f"| {g.get('id','')} | {g.get('severity','')} | {g.get('desc','')} | {g.get('found_in','')} | "
              f"{g.get('blocks','')} | {g.get('question','')} | {g.get('answered') or '—'} |")
    w("")
    w("## DRIFT log")
    w("")
    if not cfg["drifts"]:
        w("_No drift logged yet._")
    else:
        w("| Id | Description | Side A | Side B | [PROTECTED] | Decision |\n|---|---|---|---|---|---|")
        for d in cfg["drifts"]:
            w(f"| {d.get('id','')} | {d.get('desc','')} | {d.get('side_a','')} | {d.get('side_b','')} | "
              f"{'yes' if d.get('protected') else 'no'} | {d.get('decision') or '— pending'} |")
    w("")
    w("## Citation-sample checks (Phase 5 step 2)")
    w("")
    if not cfg["citation_samples"]:
        w("_Not run yet._")
    else:
        w("| Date | Scope | Sampled | Hits | Misses |\n|---|---|---|---|---|")
        for c in cfg["citation_samples"]:
            w(f"| {c.get('date','')} | {c.get('scope','')} | {c.get('sampled','')} | {c.get('hits','')} | "
              f"{'; '.join(c.get('misses', [])) or '—'} |")
    w("")
    w("## Decision log")
    w("")
    if not cfg["decisions"]:
        w("_No decisions recorded._")
    else:
        for d in cfg["decisions"]:
            w(f"- {d.get('date','')} — {d.get('decision','')} _(by {d.get('by','')})_")
    w("")
    w("## Delta rounds")
    w("")
    if not cfg["delta_rounds"]:
        w("_None yet. Run one when the code changes after a round (playbook-core §9.3)._")
    else:
        w("| Date | From | To | Stale | Cleared | Updated | Notes |\n|---|---|---|---|---|---|---|")
        for r in cfg["delta_rounds"]:
            w(f"| {r.get('date','')} | {r.get('from_ref','')} | {r.get('to_ref','')} | {r.get('stale','')} | "
              f"{r.get('cleared','')} | {r.get('updated','')} | {r.get('notes','')} |")
    w("")
    w("## Session log")
    w("")
    if not cfg["sessions"]:
        w("_No sessions recorded._")
    else:
        w("| Date | Phase | Batch | Model | Calls / cap | Tokens | Notes |\n|---|---|---|---|---|---|---|")
        for sess in cfg["sessions"]:
            calls = f"{sess['calls']} / {sess.get('cap','—')}" + (" ⛔" if sess.get("cap") and sess["calls"] >= sess["cap"] else "") if sess.get("calls") is not None else "—"
            extra = " ".join(filter(None, [f"att {sess['attempt']}" if sess.get("attempt") else "", sess.get("scope", ""), f"fix: {sess['fix']}" if sess.get("fix") else ""]))
            w(f"| {sess.get('date','')} | {sess.get('phase','')} | {sess.get('batch','') or '—'} | {sess.get('model','')} | {calls} | {sess.get('tokens') or '—'} | {(extra + ' · ') if extra else ''}{sess.get('notes','')} |")
    w("")
    w("---")
    w(f"_Generated by build_tracker.py from `run-config.json` on {date.today().isoformat()}. Edit the config, not this file._")
    return "\n".join(out)


def md_usage(cfg):
    mode = cfg["mode"]
    lenses = ", ".join(f"{l['id']} ({l['audience']})" for l in cfg["lenses"])
    op, skips = output_profile(cfg)
    d, c, s = cfg["depth"], cfg["content"], cfg["diagram_style"]
    version_line = {
        "full": "This is the **full** version: the complete 14-document corpus with a ten-minute lens per role.",
        "30min": "This is the **30-minute** version: one ~30-minute self-contained read per role over a six-document digest (`ARC`, `STR`, `FLW`, `BRI`, `UXF`, `IDX`). The full 14-document corpus was not generated; items dropped for length are marked `[PLANNED: full-depth run]`.",
        "10min": "This is the **10-minute** version: one ten-minute page per role and nothing else to read. Every claim on those pages resolves to a row in `EVIDENCE.md`. No standalone corpus documents were generated.",
    }[d]
    content_line = {
        "docs+diagrams": f"Documents and diagrams ({DSTYLES[s]}, {DDEPTHS[cfg['diagram_depth']]}).",
        "docs": "Documents only — where a diagram would sit, a table carries the same facts.",
        "diagrams": f"Diagrams are the deliverable ({DSTYLES[s]}, {DDEPTHS[cfg['diagram_depth']]}); each lens is a diagram tour. Prose documents were not written; `EVIDENCE.md` and the GAP/DRIFT logs sit behind the diagrams.",
    }[c]
    where = {
        "full": f"Open `lenses/LENS-<ID>.md` for your role ({lenses}). Each lens is a ten-minute read that begins with \"if you only read one thing\" and lists the core documents in the order that makes sense for you. Core documents live in `{cfg['output_dir']}` as `01_IDX … 14_DEP`; `01_IDX` is the index and glossary when you are not sure where to look.",
        "30min": f"Open `lenses/LENS-<ID>.md` for your role ({lenses}) — it is the main read, about 30 minutes, with an evidence appendix. The six digest documents in `{cfg['output_dir']}` are there when you need the detail behind a claim.",
        "10min": f"Open `lenses/LENS-<ID>.md` for your role ({lenses}) — ten minutes, and that is the whole read. `EVIDENCE.md` holds every claim with its citation if you want to check one.",
    }[d]
    if c == "diagrams":
        where = f"Open `lenses/LENS-<ID>.md` for your role ({lenses}) — it is a diagram tour: an ordered list of diagrams to open with one line each on what to look for. " + ("Interactive diagrams are `diagrams/<batch>.html`: click any node or edge for its evidence, switch level, filter by tag, step through a flow." if s == "interactive" else "Diagrams are in `diagrams/` (Mermaid; rendered in the HTML pages).")
    elif s == "interactive":
        where += " Interactive diagrams are `diagrams/<batch>.html`: click any node or edge for its evidence, switch level (high-level → design → tracking), filter by tag, step through a flow."
    out = f"""# How to use the {cfg['system']} documentation corpus

{version_line} {content_line}

**What this is.** One ground-truth set extracted from the code, with every non-trivial claim — and every diagram node and edge — either cited to source or marked as a gap, plus role lenses that point into it. It is not a narrative you read cover to cover; you enter through your lens and follow the citations.

## Where to start, by role

{where}

## How to read a tag

- `[src: File#Member]` — confirmed in the code at that location. Open it before relying on the claim for a change.
- `[GAP-###]` — not confirmable from what was reachable. Nothing was guessed. Check the tracker's GAP log for the question.
- `[DRIFT-###]` — two sources disagree. Both sides are stated; a decision is pending.
- `[PLANNED]` — intentionally not built yet. Different from a gap.
- `[PROTECTED]` — a rule that must survive any change; gets the most scrutiny.
- `[UNTESTED: BR-###]` / `[tested: …]` — whether an automated test exercises the rule.
- `[STALE]` — the cited file changed since the citation; treat as unverified until a delta round clears it.

A document's header carries a maturity line (`X% confirmed · Y planned · Z gap · W stale`). Low confirmation is honest, not a defect — read it as "this is how much we actually know".

## Answering a gap

Each GAP in `TRACKER.md` has a one-line question. Reply in one line (in the chat that runs the playbook, or by editing the `answered` field in `_playbook/run-config.json`). Answers are recorded as `[src: owner-answer GAP-###]` — a different kind of source from code — and if an answer contradicts the code, that becomes a DRIFT entry, not a silent correction.

## When the code changes

Do not re-run the whole playbook. Ask for a **delta round**: it diffs the code since the corpus snapshot, marks affected citations `[STALE]`, re-verifies them, documents new modules as a mini-batch, and re-samples citations. Owner answers and decisions are preserved.

## Execution mode: {"Fully Automated" if mode == "automated" else "User Monitored"}

"""
    if mode == "automated":
        out += """The playbook runs end to end without you. The tracker's **Next action** line and the batch matrix show where it is; the session log shows what ran with which model. It will interrupt only for (a) a decision it cannot undo, or (b) a `[PROTECTED]` rule found `[UNTESTED]` or in `[DRIFT]`. Everything else waits for you as the question list at the end. To switch to User Monitored mid-run, say so — the tracker records the switch and the next prompt waits for your go.
"""
    else:
        out += """You manage prompt execution. At each checkpoint the tracker's **Next action** names the exact phase and batch; the prepared prompt is offered to you, and runs only on your go — or you run it in your own Claude session and report back, in which case the tracker records what you ran. In the HTML tracker you can tick phase cells yourself; the config is updated at the next checkpoint. To switch to Fully Automated, say so; the run continues from the current next action.
"""
    prof = cfg["cost_profile"]
    res = cfg["resolved_models"]
    out += f"""
## Audit effort: {AUDIT[cfg['audit_depth']].split(' — ')[0]}

{ {"none": "No independent audit was run — only the mechanical doc_check (citations resolve, no hedging, tags reconcile). Treat every claim as unverified beyond that.", "low": "A fresh auditor confirmed a random citation sample mechanically; nothing outside the sample was checked.", "medium": "A fresh auditor confirmed a citation sample, ran the consistency checks and tried to falsify five claims of its own choosing; the tracker shows the hit rate.", "high": "A fresh auditor read the whole corpus and repository; the tracker shows the hit rate and what it read."}[cfg['audit_depth']] } Every extraction phase also ended with `doc_check.py`: unresolved citations and hedging words block a checkpoint.
"""
    out += f"""
## Cost profile: {PROFILES[prof]}

Each phase runs on the model and effort the playbook recommends for it, shifted by this profile. The orchestrator launches a separate agent per phase with that model: this run uses {', '.join(f'{pid} → {res[pid]["model"]}/{res[pid]["effort"]}' for pid in sorted(res))}. The tracker's phase table shows recommended, resolved and actually-used side by side, so a budget run is never mistaken for a recommended one. To change the profile for the phases not yet started, say so — it is recorded as a decision.
"""
    out += """
## Files

- `TRACKER.md` / `TRACKER.html` — where the run is: phases, batches, gaps, drift, decisions, citation checks, sessions.
- `_playbook/run-config.json` — the tracker's source of truth. Edit this (or ask), then regenerate with `build_tracker.py`.
- `lenses/` — one file per active lens.
""" + {"full": "- `01_IDX.md … 14_DEP.md` — the core corpus. HTML pages, when generated, sit beside them with the same names.",
            "30min": "- `ARC.md`, `STR.md`, `FLW.md`, `BRI.md`, `UXF.md`, `IDX.md` — the six-document digest.",
            "10min": "- `EVIDENCE.md` — every claim the lens pages make, with its citation and tags, grouped by lens."}[cfg["depth"]] + ("\n- `diagrams/` — the diagram set" + (" (`<batch>.json` + interactive `<batch>.html`)." if cfg["diagram_style"] == "interactive" else " (Mermaid sources; rendered in the HTML pages).") if cfg["content"] != "docs" else "") + """
"""
    return out


# ---------------------------------------------------------------- HTML
CSS = """
:root{--bg:#12151C;--surface:#1B212C;--surface-2:#212837;--border:#2A3140;--text:#E8EAED;--text-2:#96A0B3;--text-3:#5A6272;
--teal:#4FD1C5;--teal-dim:rgba(79,209,197,.12);--amber:#E8A33D;--amber-dim:rgba(232,163,61,.12);--coral:#E8735C;--coral-dim:rgba(232,115,92,.14);
--blue:#7C9CE8;--blue-dim:rgba(124,156,232,.12);--sans:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;--mono:'IBM Plex Mono',SF Mono,Consolas,monospace}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F7F9;--surface:#fff;--surface-2:#EEF1F5;--border:#D9DEE6;--text:#1B2230;--text-2:#4B5565;--text-3:#8A93A3;--teal:#0E8F84;--teal-dim:rgba(14,143,132,.1);--amber:#B86E0A;--amber-dim:rgba(184,110,10,.1);--coral:#C4462C;--coral-dim:rgba(196,70,44,.1);--blue:#3A5BC7;--blue-dim:rgba(58,91,199,.1)}}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14.5px;line-height:1.6}
.wrap{max-width:1180px;margin:0 auto;padding:32px 16px 96px}h1{font-size:26px;margin-bottom:6px}h2{font-size:18px;margin:36px 0 10px;display:flex;align-items:center;gap:10px}
h2 .n{font-family:var(--mono);color:var(--text-3);font-size:13px;font-weight:500}.sub{color:var(--text-2);font-size:13.5px;margin-bottom:14px}
.next{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--teal);border-radius:8px;padding:14px 18px;margin:18px 0 8px}
.next b{color:var(--teal);font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;display:block;margin-bottom:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}.card .k{font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:.07em}
.card .v{font-size:20px;font-weight:600;margin-top:4px}.card .v.warn{color:var(--coral)}.card .v.ok{color:var(--teal)}
.tbl{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--surface)}table{width:100%;border-collapse:collapse;font-size:13.2px}
th{text-align:left;background:var(--surface-2);color:var(--text-3);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:10px 12px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid var(--border);color:var(--text-2);vertical-align:top}tr:last-child td{border-bottom:none}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-2);white-space:nowrap;cursor:default}
.pill.done{color:var(--teal);background:var(--teal-dim);border-color:var(--teal)}.pill.in_progress{color:var(--amber);background:var(--amber-dim);border-color:var(--amber)}
.pill.blocked{color:var(--coral);background:var(--coral-dim);border-color:var(--coral)}.pill.skipped{opacity:.5}
.pill.click{cursor:pointer}.sev-Blocking{color:var(--coral);font-weight:600}.sev-High{color:var(--amber);font-weight:600}.sev-Low{color:var(--text-3)}
code{font-family:var(--mono);font-size:12.3px;background:var(--surface-2);padding:1px 5px;border-radius:4px}.muted{color:var(--text-3);font-size:13px}
.star{color:var(--amber)}footer{margin-top:40px;color:var(--text-3);font-size:12px}.kv td:first-child{color:var(--text-3);white-space:nowrap;width:180px}
ol,ul{padding-left:22px;color:var(--text-2)}li{margin:4px 0}p{color:var(--text-2);margin:8px 0}
"""


def pill(status, clickable=False, data=""):
    cls = "pill " + status + (" click" if clickable else "")
    return f'<span class="{cls}" {data}>{STATUS_MARK.get(status, "")} {html.escape(status)}</span>'


def esc(x):
    return html.escape(str(x if x is not None else ""))


def html_shell(title, body, extra_js=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">{body}</div><script>{extra_js}</script></body></html>"""


def html_tracker(cfg):
    s = summarise(cfg)
    mode_label = "Fully Automated" if cfg["mode"] == "automated" else "User Monitored"
    b = []
    w = b.append
    w(f"<h1>Playbook Execution Tracker — {esc(cfg['system'])}</h1>")
    w(f'<div class="sub">{mode_label} · {esc(cfg["format"].upper())} · started {esc(cfg["started"])} · corpus describes {esc(cfg.get("corpus_ref") or "— (set in Phase 0)")}</div>')
    w(f'<div class="next"><b>Next action</b>{esc(cfg["next_action"])}</div>')
    w('<div class="grid">')
    w(f'<div class="card"><div class="k">Batches complete</div><div class="v">{s["batches_done"]}/{s["batches"]}</div></div>')
    w(f'<div class="card"><div class="k">Open Blocking / High</div><div class="v {"warn" if s["open_blocking"] or s["open_high"] else "ok"}">{s["open_blocking"]} / {s["open_high"]}</div></div>')
    w(f'<div class="card"><div class="k">Low · answered</div><div class="v">{s["open_low"]} · {s["answered"]}</div></div>')
    w(f'<div class="card"><div class="k">Undecided drift</div><div class="v {"warn" if s["drifts_protected"] else ""}">{s["drifts_open"]} <span class="muted">({s["drifts_protected"]} protected)</span></div></div>')
    w(f'<div class="card"><div class="k">Citation hit rate</div><div class="v">{esc(s["hit_rate"])}</div></div>')
    w(f'<div class="card"><div class="k">Calls · cap hits</div><div class="v {"warn" if s["cap_hits"] else ""}">{s["calls_total"]} · {s["cap_hits"]}</div></div>')
    w(f'<div class="card"><div class="k">Cards open</div><div class="v {"amber" if s["cards_open"] else "ok"}">{s["cards_open"]} <span class="muted">· {s["cards_auto"]} auto</span></div></div>')
    w('</div>')

    w('<h2><span class="n">01</span>Run configuration</h2><div class="tbl"><table class="kv">')
    rows = [("Mode", mode_label), ("Output format", cfg["format"].upper()), ("Output location", f"<code>{esc(cfg['output_dir'])}</code>"),
            ("Target access", esc(cfg.get("target", "—"))),
            ("Cost profile", f'<span class="pill in_progress">{esc(PROFILES[cfg["cost_profile"]])}</span>'),
            ("Output profile", " ".join(f'<span class="pill">{esc(x)}</span>' for x in output_profile(cfg)[0].split(" · ")) + (f' <span class="muted">skips Phase {esc(", ".join(output_profile(cfg)[1]))}</span>' if output_profile(cfg)[1] else "")),
            ("Audit effort", f'<span class="pill {"blocked" if cfg["audit_depth"] == "none" else "in_progress"}">{esc(AUDIT[cfg["audit_depth"]])}</span>'),
            ("Call budget per phase", " ".join(f'<span class="pill">{esc(k)} {v}</span>' for k, v in cfg["budget_calls"].items() if v) + ' <span class="muted">cap hit → clean handoff + Decision Card</span>'),
            ("Active lenses", " ".join(f'<span class="pill">{esc(l["id"])}</span>' for l in cfg["lenses"])),
            ("Seed [PROTECTED]", esc(len(cfg["seed_invariants"]) or "none — Phase 2 proposes candidates"))]
    if cfg.get("summary"):
        rows.append(("Owner summary", esc(cfg["summary"]) + ' <span class="muted">(context, not evidence)</span>'))
    for k, v in rows:
        w(f"<tr><td>{k}</td><td>{v}</td></tr>")
    w("</table></div>")
    if cfg["seed_invariants"]:
        w("<ol>" + "".join(f"<li><code>[PROTECTED]</code> {esc(i)}</li>" for i in cfg["seed_invariants"]) + "</ol>")

    w('<h2><span class="n">02</span>Phase plan, model &amp; effort</h2>')
    w(f'<div class="sub">Cost profile <b>{esc(PROFILES[cfg["cost_profile"]])}</b> — the orchestrator launches each phase\'s agent with the <i>resolved</i> model/effort; <i>used</i> comes from the session log. ⚑ critical phase.</div>')
    w('<div class="tbl"><table><tr><th>Phase</th><th>Scope</th><th>Recommended</th><th>Resolved</th><th>Used</th><th>Status</th></tr>')
    used = used_models(cfg)
    for pid, name, scope in PHASES:
        m = cfg["models"][pid]; r = cfg["resolved_models"][pid]
        if pid in RUN_PHASES:
            st = cfg["phase_status"][pid]
            cell = pill(st, True, f'data-kind="run" data-phase="{pid}"')
        else:
            vals = [x["phases"][pid] for x in cfg["batches"]]
            st = "pending" if not vals else ("skipped" if all(v == "skipped" for v in vals) else "done" if all(v in ("done", "skipped") for v in vals) else "in_progress" if any(v not in ("pending", "skipped") for v in vals) else "pending")
            cell = pill(st)
        crit = ' <span class="star">⚑</span>' if m.get("critical") else ""
        note = f' <span class="muted">({esc(m["note"])})</span>' if m.get("note") else ""
        w(f"<tr><td><b>{pid}</b> — {esc(name)}{crit}</td><td>{esc(scope)}</td><td>{esc(m['tier'])} / {esc(m['effort'])}{note}</td>"
          f"<td><span class='pill done'>{esc(r['model'])}</span> <span class='pill'>{esc(r['effort'])}</span></td><td>{esc(', '.join(used.get(pid, [])) or '—')}</td><td>{cell}</td></tr>")
        if pid == "5":
            mr = cfg["models"]["5re"]; rr = cfg["resolved_models"]["5re"]
            w(f"<tr><td><b>5</b> — scoped re-audit</td><td>per failed audit</td><td>{esc(mr['tier'])} / {esc(mr['effort'])} <span class='muted'>({esc(mr.get('note',''))})</span></td><td><span class='pill done'>{esc(rr['model'])}</span> <span class='pill'>{esc(rr['effort'])}</span></td><td>{esc(', '.join(used.get('5re', [])) or '—')}</td><td>—</td></tr>")
    w("</table></div>")

    w('<h2><span class="n">03</span>Batch × phase matrix</h2>')
    if not cfg["batches"]:
        w('<p class="muted">Batch plan not yet produced — Phase 0 fills this in.</p>')
    else:
        w('<div class="sub">Click a cell to cycle its status locally (pending → in progress → done → blocked). Local ticks are remembered in this browser only; the config is updated at the next checkpoint.</div>')
        w('<div class="tbl"><table><tr><th>Batch</th><th>Modules</th><th>Ph 1</th><th>Ph 2</th><th>Ph 3</th><th>Ph 4</th></tr>')
        for i, x in enumerate(cfg["batches"]):
            name = ('<span class="star">★</span> ' if x["pilot"] else "") + esc(x["name"])
            cells = "".join(f"<td>{pill(x['phases'][p], True, f'data-kind=\"batch\" data-batch=\"{i}\" data-phase=\"{p}\"')}</td>" for p in BATCH_PHASES)
            w(f"<tr><td>{name}</td><td>{esc(', '.join(x['modules']) or '—')}</td>{cells}</tr>")
        w("</table></div><p class='muted'>★ pilot batch — runs Phases 1–5 before any other batch starts.</p>")

    w('<h2><span class="n">03b</span>Decision cards</h2>')
    if not cfg["decision_cards"]: w('<p class="muted">None raised yet. DC-000 approves the batch plan at the end of Phase 0.</p>')
    else:
        w('<div class="tbl"><table><tr><th>Id</th><th>Title</th><th>Between</th><th>Status</th><th>Stops run</th><th>Decision</th><th>By / rule</th><th>Date</th></tr>')
        for c in cfg["decision_cards"]:
            by = esc(c.get("by")) or (f"AUTO rule {esc(c['rule'])}" if c.get("rule") else "—")
            w(f"<tr><td><a href='decisions/{esc(c.get('id'))}.html' style='color:var(--teal)'>{esc(c.get('id'))}</a></td><td>{esc(c.get('title'))}</td><td>{esc(c.get('between'))}</td><td><span class='pill {esc(c.get('status',''))}'>{esc(c.get('status'))}</span></td><td>{'<span class=\"sev-Blocking\">yes</span>' if c.get('stops_run') else 'no'}</td><td>{esc(c.get('decision') or '—')}</td><td>{by}</td><td>{esc(c.get('date'))}</td></tr>")
        w("</table></div>")
    w('<h2><span class="n">03c</span>doc_check history</h2>')
    if not cfg["checks"]: w('<p class="muted">No checks recorded. Run <code>scripts/doc_check.py</code> at the end of every extraction phase.</p>')
    else:
        w('<div class="tbl"><table><tr><th>#</th><th>Batch</th><th>Date</th><th>Citations</th><th>Resolved</th><th>Unresolved</th><th>Hedges</th><th>Untraced</th><th>Status</th></tr>')
        for c in cfg["checks"]:
            w(f"<tr><td>{esc(c.get('check'))}</td><td>{esc(c.get('batch') or '—')}</td><td>{esc(c.get('date'))}</td><td>{esc(c.get('citations_total'))}</td><td>{esc(c.get('resolved'))}</td><td>{esc(c.get('unresolved'))}</td><td>{esc(c.get('hedges'))}</td><td>{esc(c.get('untraced'))}</td><td>{pill('blocked') if c.get('blocking') else pill('done')}</td></tr>")
        w("</table></div>")
    w('<h2><span class="n">04</span>GAP log</h2>')
    if not cfg["gaps"]:
        w('<p class="muted">No gaps logged yet.</p>')
    else:
        order = {"Blocking": 0, "High": 1, "Low": 2}
        w('<div class="tbl"><table><tr><th>Id</th><th>Sev</th><th>Description</th><th>Found in</th><th>Blocks</th><th>Question</th><th>Answered</th></tr>')
        for g in sorted(cfg["gaps"], key=lambda g: (bool(g.get("answered")), order.get(g.get("severity"), 3), g.get("id", ""))):
            w(f"<tr><td><code>{esc(g.get('id'))}</code></td><td class='sev-{esc(g.get('severity'))}'>{esc(g.get('severity'))}</td><td>{esc(g.get('desc'))}</td>"
              f"<td>{esc(g.get('found_in'))}</td><td>{esc(g.get('blocks'))}</td><td>{esc(g.get('question'))}</td><td>{esc(g.get('answered') or '—')}</td></tr>")
        w("</table></div>")

    w('<h2><span class="n">05</span>DRIFT log</h2>')
    if not cfg["drifts"]:
        w('<p class="muted">No drift logged yet.</p>')
    else:
        w('<div class="tbl"><table><tr><th>Id</th><th>Description</th><th>Side A</th><th>Side B</th><th>[PROTECTED]</th><th>Decision</th></tr>')
        for d in cfg["drifts"]:
            w(f"<tr><td><code>{esc(d.get('id'))}</code></td><td>{esc(d.get('desc'))}</td><td>{esc(d.get('side_a'))}</td><td>{esc(d.get('side_b'))}</td>"
              f"<td>{'<span class=\"sev-High\">yes</span>' if d.get('protected') else 'no'}</td><td>{esc(d.get('decision') or '— pending')}</td></tr>")
        w("</table></div>")

    w('<h2><span class="n">06</span>Citation-sample checks</h2>')
    if not cfg["citation_samples"]:
        w('<p class="muted">Not run yet (Phase 5 step 2).</p>')
    else:
        w('<div class="tbl"><table><tr><th>Date</th><th>Scope</th><th>Sampled</th><th>Hits</th><th>Misses</th></tr>')
        for c in cfg["citation_samples"]:
            w(f"<tr><td>{esc(c.get('date'))}</td><td>{esc(c.get('scope'))}</td><td>{esc(c.get('sampled'))}</td><td>{esc(c.get('hits'))}</td><td>{esc('; '.join(c.get('misses', [])) or '—')}</td></tr>")
        w("</table></div>")

    w('<h2><span class="n">07</span>Decisions</h2>')
    w("<ul>" + "".join(f"<li>{esc(d.get('date'))} — {esc(d.get('decision'))} <span class='muted'>(by {esc(d.get('by'))})</span></li>" for d in cfg["decisions"]) + "</ul>"
      if cfg["decisions"] else '<p class="muted">No decisions recorded.</p>')

    w('<h2><span class="n">08</span>Delta rounds</h2>')
    if not cfg["delta_rounds"]:
        w('<p class="muted">None yet. Run one when the code changes after a round.</p>')
    else:
        w('<div class="tbl"><table><tr><th>Date</th><th>From</th><th>To</th><th>Stale</th><th>Cleared</th><th>Updated</th><th>Notes</th></tr>')
        for r in cfg["delta_rounds"]:
            w("<tr>" + "".join(f"<td>{esc(r.get(k))}</td>" for k in ("date", "from_ref", "to_ref", "stale", "cleared", "updated", "notes")) + "</tr>")
        w("</table></div>")

    w('<h2><span class="n">09</span>Session log</h2>')
    if not cfg["sessions"]:
        w('<p class="muted">No sessions recorded.</p>')
    else:
        w('<div class="tbl"><table><tr><th>Date</th><th>Phase</th><th>Batch</th><th>Model</th><th>Calls / cap</th><th>Tokens</th><th>Notes</th></tr>')
        for sess in cfg["sessions"]:
            hit = sess.get("calls") is not None and sess.get("cap") and sess["calls"] >= sess["cap"]
            calls = f"<span class='{'sev-Blocking' if hit else ''}'>{sess['calls']} / {sess.get('cap','—')}</span>" if sess.get("calls") is not None else "—"
            w(f"<tr><td>{esc(sess.get('date'))}</td><td>{esc(sess.get('phase'))}</td><td>{esc(sess.get('batch') or '—')}</td><td>{esc(sess.get('model'))}</td><td>{calls}</td><td>{esc(sess.get('tokens') or '—')}</td><td>{esc(sess.get('notes'))}</td></tr>")
        w("</table></div>")
    w(f"<footer>Generated by build_tracker.py from <code>run-config.json</code> on {date.today().isoformat()}. Edit the config, not this file.</footer>")

    js = f"""
(function(){{
  var KEY='tracker:{esc(cfg["system"])}', ORDER=['pending','in_progress','done','blocked'];
  var MARK={json.dumps(STATUS_MARK)};
  var saved={{}}; try{{saved=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
  function key(el){{return el.dataset.kind+':'+(el.dataset.batch||'')+':'+el.dataset.phase}}
  function apply(el,st){{el.className='pill click '+st; el.textContent=(MARK[st]||'')+' '+st.replace('_',' ')}}
  document.querySelectorAll('.pill.click').forEach(function(el){{
    var k=key(el); if(saved[k]) apply(el,saved[k]);
    el.addEventListener('click',function(){{
      var cur=ORDER.indexOf((el.className.match(/pending|in_progress|done|blocked/)||['pending'])[0]);
      var nxt=ORDER[(cur+1)%ORDER.length]; apply(el,nxt); saved[k]=nxt;
      try{{localStorage.setItem(KEY,JSON.stringify(saved))}}catch(e){{}}
    }});
  }});
}})();"""
    return html_shell(f"Tracker — {cfg['system']}", "".join(b), js)


def html_usage(cfg):
    # Minimal markdown→html for the usage guide (headings, lists, paragraphs, code spans, bold).
    import re
    md = md_usage(cfg)
    out, in_list = [], False
    def inline(t):
        t = esc(t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        return t
    for line in md.splitlines():
        if line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>"); continue
        if line.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h2>{inline(line[3:])}</h2>"); continue
        if line.startswith("- "):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(line[2:])}</li>"); continue
        if in_list and not line.strip():
            out.append("</ul>"); in_list = False; continue
        if line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_list: out.append("</ul>")
    return html_shell(f"Usage — {cfg['system']}", "".join(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("--out", default=None, help="output directory (default: config's output_dir)")
    ap.add_argument("--format", choices=["md", "html", "both"], default=None, help="override config format")
    a = ap.parse_args()
    cfg = load(a.config)
    fmt = a.format or cfg["format"]
    out = a.out or cfg["output_dir"]
    os.makedirs(out, exist_ok=True)
    written = []
    if fmt in ("md", "both"):
        for name, content in (("TRACKER.md", md_tracker(cfg)), ("USAGE.md", md_usage(cfg))):
            p = os.path.join(out, name); open(p, "w", encoding="utf-8").write(content); written.append(p)
    if fmt in ("html", "both"):
        for name, content in (("TRACKER.html", html_tracker(cfg)), ("USAGE.html", html_usage(cfg))):
            p = os.path.join(out, name); open(p, "w", encoding="utf-8").write(content); written.append(p)
    s = summarise(cfg)
    print("wrote: " + ", ".join(written))
    print(f"batches {s['batches_done']}/{s['batches']} · open Blocking {s['open_blocking']} High {s['open_high']} Low {s['open_low']} · hit rate {s['hit_rate']}")
    print(f"next: {cfg['next_action']}")


if __name__ == "__main__":
    main()
