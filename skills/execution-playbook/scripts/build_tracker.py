#!/usr/bin/env python3
"""
build_tracker.py — render the execution-playbook tracker and the short usage guide from
run-config.json. The config is the source of truth (it is the run's STATE); the tracker files
are views. Re-run after every stage / gate / decision; outputs are overwritten.

Usage:
    python3 build_tracker.py run-config.json [--out DIR] [--format md|html|both]

Config schema (all keys optional except "task"; see assets/run-config.example.json):
{
  "task": "short task name",
  "goal": "one-paragraph goal (Phase 0)",
  "target": "how the target is reached",
  "summary": "confirmed summary — intent, not evidence (mandatory)",
  "summary_sources": ["user", "document: <name>", "suggested"],
  "expected_output": [ {"artefact","where","check"} ],            # mandatory; becomes the top of the DoD
  "stack": ["..."],                                               # named by the user or confirmed from the technology suggestion
  "fidelity": "poc" | "mvp" | "full",                             # default mvp
  "effort": { "logic": "very-low|recommended|rich", "architecture": "...", "ui": "...|n/a" },
  "review_depth": "none" | "low" | "medium" | "high",             # reviewer effort; default low for poc, medium otherwise
  "self_check": "minimal" | "standard" | "tool",                   # build self-check; default minimal for poc, standard otherwise
                                                                 # per-WP gate may add: "first_review":"PASS|FAIL", "mutation":{"listed":N,"survived":N,"tests_added":N,"kill_rate":"82%"}
  "tooling": "claude-only" | [ {"tool","used_for","wps":[...],"availability":"available|needs-setup|missing","produces"} ],
  "mode": "automated" | "monitored",
  "format": "md" | "html" | "both",
  "output_dir": "_playbook/",
  "started": "YYYY-MM-DD",
  "spec_ref": "commit / spec version the run is built against",
  "budget": "free text, e.g. 2 fix loops",
  "budget_calls": {"design":12,"build":25,"fix":15,"review":12,"integrate":6},   # per-stage tool-call caps; defaults by fidelity
  "locked_decisions": ["..."],
  "non_goals": ["..."],
  "definition_of_done": ["..."],
  "cost_profile": "very-low" | "recommended" | "rich",           # default recommended
  "lenses": [ {"id","perspective","checks":[...]} ],            # defaults added if absent
  "models": { "0": {"tier":"mid","effort":"high","critical":false}, ... },   # RECOMMENDED per phase; defaults added if absent
                                                                 # tiers small|mid|strong|top; efforts low|medium|high|xhigh|max
                                                                 # "3" is the review; "3fix" the fix loop. Resolved values are computed.
  "decision_rules": ["..."],                                     # defaults added if absent
  "phase_status": { "0": "done", "5": "pending", "6": "pending" },
  "work_packages": [ {"id":"WP-01","name","depends_on":[...],"pilot":true,"budget":"",
                      "stages": {"design":"done","build":"done","verify":"in_progress","integrate":"pending"},
                      "gate": {"attempts":1,"fix_loops":0,"commands":"PASS","review":"FAIL","blocked":false},
                      "ac_total":5,"ac_tested":3} ],
  "decision_cards": [ {"id":"DC-003","title","wp","between","status":"OPEN|DECIDED|AUTO-DECIDED|SUPERSEDED",
                       "stops_run":true,"decision":"B","by":"Mahdi","rule":null,"date"} ],
  "adrs":   [ {"id","title","status":"Proposed|Accepted|Superseded","dc"} ],
  "gaps":   [ {"id","desc","severity","found_in","blocks","question","answered"} ],
  "drifts": [ {"id","desc","side_a","side_b","protected":bool,"decision"} ],
  "risks":  [ {"id","risk","likelihood","impact","trigger","mitigation","owner"} ],
  "citation_samples": [ {"date","scope","sampled","hits","misses":[...]} ],
  "sessions": [ {"date","phase","wp","model","calls":17,"cap":25,"tokens":41000,"attempt":1,"scope":"full|scoped","fix":"continued|fresh","notes"} ],
  "budget_tokens_continue": 150000,                                # fix continues the builder only under this conversation size
  "delta_rounds": [ {"date","from_ref","to_ref","stale","redesigned","regated","notes"} ],
  "next_action": "the exact next prompt / card to run or answer"
}
Status values: pending | in_progress | done | blocked | skipped
"""
import argparse, html, json, os, sys
from datetime import date

PHASES = [
    ("0", "Frame & work packages", "per run"),
    ("1", "Design", "per WP"),
    ("2", "Build (tests first)", "per WP"),
    ("3", "Verify (gate + review)", "per WP"),
    ("4", "Decision card & integrate", "per WP"),
    ("5", "Final audit", "per run"),
    ("6", "Handover", "per run"),
]
STAGES = [("design", "Design"), ("build", "Build"), ("verify", "Verify"), ("integrate", "Integrate")]
RUN_PHASES = ["0", "5", "6"]
STAGE_TO_PHASE = {"design": "1", "build": "2", "verify": "3", "integrate": "4"}

DEFAULT_LENSES = [
    {"id": "CORRECTNESS", "perspective": "Does it do what the ACs say — and nothing else?",
     "checks": ["each AC has a test that can fail", "edge cases covered or [PLANNED]", "spec mismatches are [DRIFT]"]},
    {"id": "SECURITY", "perspective": "Can it be misused, or does it trust what it should verify?",
     "checks": ["server-side authz at every entry", "input validation at boundary", "no secrets committed", "deps pinned"]},
    {"id": "MAINTAINABILITY", "perspective": "Will the next person understand and safely change it?",
     "checks": ["follows CLAUDE.md conventions", "no duplicated logic", "non-obvious choices have an ADR", "tests read as spec"]},
    {"id": "OPERABILITY", "perspective": "Can it be run, observed and recovered?",
     "checks": ["config externalised", "failures logged with context", "timeouts/retries/idempotency", "reversible migrations or [RISK]"]},
]
DEFAULT_MODELS = {
    "0": {"tier": "mid", "effort": "high", "critical": False, "note": "strong if protected/irreversible areas"},
    "1": {"tier": "mid", "effort": "high", "critical": False, "note": "strong for risky WPs"},
    "2": {"tier": "mid", "effort": "high", "critical": False, "note": "small for boilerplate"},
    "3": {"tier": "strong", "effort": "xhigh", "critical": True, "note": "review, fresh context"},
    "3fix": {"tier": "mid", "effort": "high", "critical": False, "note": "fix loop; continues the builder"},
    "3re": {"tier": "mid", "effort": "high", "critical": False, "note": "scoped re-review; escalates to '3' on a trigger"},
    "4": {"tier": "small", "effort": "medium", "critical": False},
    "5": {"tier": "strong", "effort": "xhigh", "critical": True, "note": "fresh context"},
    "6": {"tier": "mid", "effort": "high", "critical": False},
}
TIERS = ["small", "mid", "strong", "top"]
TIER_NAMES = {"small": "haiku", "mid": "sonnet", "strong": "opus", "top": "fable"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
PROFILES = {"very-low": "Very Low Budget", "recommended": "Recommended", "rich": "I Am Too Rich"}
FIDELITY = {"poc": "Fastest POC", "mvp": "MVP", "full": "Full implementation"}
EFFORT = {"very-low": "Very Low", "recommended": "Recommended", "rich": "I Am Too Rich", "n/a": "n/a"}
EFFORT_DIMS = [("logic", "Logic"), ("architecture", "Architecture & solution design"), ("ui", "UI design")]
CALL_BUDGETS = {"poc": {"design": 8, "build": 15, "fix": 10, "review": 8, "rereview": 6, "integrate": 4},
                "mvp": {"design": 12, "build": 25, "fix": 15, "review": 12, "rereview": 8, "integrate": 6},
                "full": {"design": 16, "build": 35, "fix": 20, "review": 20, "rereview": 12, "integrate": 6}}
SELFCHECK = {"minimal": "Minimal — fail-first evidence only", "standard": "Standard — mutation sweep + control tests", "tool": "Tool-backed — sweep + mutation tool per gate"}
BUDGET = {"poc": "≤10 unit / ≤3 e2e per WP", "mvp": "15–40 unit / ≤10 e2e per WP", "full": "30–80 unit / ≤15 e2e per WP", "rich": "no upper bound (property-based); every test listed"}
REVIEW = {"none": "None — no independent review", "low": "Low — ACs + diff (~5–10k/review)", "medium": "Medium — context pack (~15–30k/review)", "high": "High — full reading (~80–360k/review)"}


def resolve_models(cfg):
    """Apply the cost profile to the recommended per-phase tier/effort. Rules: cost-and-orchestration.md §2."""
    prof = cfg.get("cost_profile", "recommended"); out = {}
    for pid, m in cfg["models"].items():
        t = TIERS.index(m["tier"]) if m["tier"] in TIERS else 1
        e = EFFORTS.index(m["effort"]) if m["effort"] in EFFORTS else 2
        crit = bool(m.get("critical"))
        if prof == "very-low":
            t = max(t - 2, TIERS.index("mid") if crit else 0); e = max(e - 1, EFFORTS.index("medium") if crit else 0)
        elif prof == "rich":
            if t < len(TIERS) - 1: t += 1
            else: e = min(e + 1, len(EFFORTS) - 1)
        out[pid] = {"tier": TIERS[t], "model": TIER_NAMES[TIERS[t]], "effort": EFFORTS[e]}
    return out


def used_models(cfg):
    used = {}
    for s in cfg.get("sessions", []):
        p = str(s.get("phase", "")).strip()
        if p and s.get("model"):
            used.setdefault(p, [])
            if s["model"] not in used[p]: used[p].append(s["model"])
    return used
DEFAULT_RULES = [
    "The spec wins; conflicts logged in DECISIONS.md",
    "Never invent — missing facts become [GAP]",
    "Contradictions become [DRIFT], presented both ways",
    "Ambiguous technical choice → simplest option meeting the ACs, one line of reasoning",
    "Never weaken a gate; mark [BLOCKED] instead",
    "No dependencies beyond the locked stack (dev-only gate tooling excepted, logged)",
    "Irreversible actions stop the run for a human",
    "Budget overrun stops the run for a human",
    "Commit per passed WP: 'WP-NN: <name> (PASS)'",
]
MARK = {"pending": "☐", "in_progress": "◐", "done": "☑", "blocked": "⛔", "skipped": "–"}


def load(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if "task" not in cfg:
        sys.exit('config needs at least a "task" name')
    cfg.setdefault("mode", "monitored"); cfg.setdefault("format", "both"); cfg.setdefault("output_dir", "_playbook/")
    cfg.setdefault("started", date.today().isoformat())
    for k in ("locked_decisions", "non_goals", "definition_of_done", "decision_cards", "adrs", "gaps", "drifts",
              "risks", "citation_samples", "sessions", "delta_rounds", "work_packages"):
        cfg.setdefault(k, [])
    cfg.setdefault("lenses", [])
    if not {l["id"] for l in cfg["lenses"]} & {d["id"] for d in DEFAULT_LENSES}:
        cfg["lenses"] = DEFAULT_LENSES + cfg["lenses"]
    models = {k: dict(v) for k, v in DEFAULT_MODELS.items()}
    for k, v in cfg.get("models", {}).items():
        models.setdefault(k, {}).update(v)
    cfg["models"] = models
    cfg.setdefault("cost_profile", "recommended")
    if cfg["cost_profile"] not in PROFILES:
        sys.exit(f"cost_profile must be one of {list(PROFILES)}")
    cfg["resolved_models"] = resolve_models(cfg)
    cfg.setdefault("summary_sources", []); cfg.setdefault("expected_output", []); cfg.setdefault("stack", [])
    cfg.setdefault("fidelity", "mvp")
    if cfg["fidelity"] not in FIDELITY: sys.exit(f"fidelity must be one of {list(FIDELITY)}")
    eff = {"logic": "recommended", "architecture": "recommended", "ui": "recommended"}
    if cfg["fidelity"] == "poc": eff = {k: "very-low" for k in eff}
    eff.update(cfg.get("effort", {})); cfg["effort"] = eff
    for k, v in eff.items():
        if v not in EFFORT: sys.exit(f"effort.{k} must be one of {list(EFFORT)}")
    cfg.setdefault("tooling", "claude-only")
    cfg.setdefault("review_depth", "low" if cfg["fidelity"] == "poc" else "medium")
    if cfg["review_depth"] not in REVIEW: sys.exit(f"review_depth must be one of {list(REVIEW)}")
    cfg.setdefault("self_check", "minimal" if cfg["fidelity"] == "poc" else "standard")
    if cfg["self_check"] not in SELFCHECK: sys.exit(f"self_check must be one of {list(SELFCHECK)}")
    bc = dict(CALL_BUDGETS[cfg["fidelity"]])
    if cfg.get("review_depth") == "high": bc["review"] += 10
    bc.update(cfg.get("budget_calls", {})); cfg["budget_calls"] = bc
    cfg["test_budget"] = BUDGET["rich"] if (cfg["effort"]["logic"] == "rich" and cfg["fidelity"] != "poc") else BUDGET[cfg["fidelity"]]
    cfg.setdefault("decision_rules", DEFAULT_RULES)
    ps = {p: "pending" for p in RUN_PHASES}; ps.update(cfg.get("phase_status", {})); cfg["phase_status"] = ps
    for wp in cfg["work_packages"]:
        wp.setdefault("depends_on", []); wp.setdefault("pilot", False); wp.setdefault("budget", "")
        st = {s: "pending" for s, _ in STAGES}; st.update(wp.get("stages", {})); wp["stages"] = st
        g = {"attempts": 0, "fix_loops": 0, "commands": "", "review": "", "blocked": False}; g.update(wp.get("gate", {})); wp["gate"] = g
        if g["blocked"]:
            wp["stages"]["verify"] = "blocked"
    cfg.setdefault("next_action", "Run Phase 0 (frame the task, propose work packages, raise DC-000).")
    return cfg


def summarise(cfg):
    wps = cfg["work_packages"]
    gaps = cfg["gaps"]; open_gaps = [g for g in gaps if not g.get("answered")]
    cards = cfg["decision_cards"]
    s = {
        "wps": len(wps),
        "wps_done": sum(1 for w in wps if all(v == "done" for v in w["stages"].values())),
        "wps_blocked": sum(1 for w in wps if w["gate"]["blocked"]),
        "gate_attempts": sum(w["gate"]["attempts"] for w in wps),
        "gate_passed": sum(1 for w in wps if w["stages"]["verify"] == "done"),
        "review_first_avg": (lambda xs: round(sum(xs) / len(xs)) if xs else 0)([x["tokens"] for x in cfg["sessions"] if str(x.get("phase")) == "3" and x.get("tokens") and (x.get("attempt") or 1) == 1]),
        "review_re_avg": (lambda xs: round(sum(xs) / len(xs)) if xs else 0)([x["tokens"] for x in cfg["sessions"] if str(x.get("phase")) == "3" and x.get("tokens") and (x.get("attempt") or 1) > 1]),
        "re_scoped": sum(1 for x in cfg["sessions"] if str(x.get("phase")) == "3" and (x.get("attempt") or 1) > 1 and x.get("scope") == "scoped"),
        "re_full": sum(1 for x in cfg["sessions"] if str(x.get("phase")) == "3" and (x.get("attempt") or 1) > 1 and x.get("scope") == "full"),
        "fix_continued": sum(1 for x in cfg["sessions"] if x.get("fix") == "continued"),
        "fix_fresh": sum(1 for x in cfg["sessions"] if x.get("fix") == "fresh"),
        "cap_hits": sum(1 for x in cfg["sessions"] if x.get("calls") is not None and x.get("cap") and x["calls"] >= x["cap"]),
        "calls_total": sum(x.get("calls") or 0 for x in cfg["sessions"]),
        "gated": sum(1 for w in wps if w["gate"]["attempts"] > 0),
        "first_pass": sum(1 for w in wps if w["gate"]["attempts"] > 0 and (w["gate"].get("first_review") == "PASS" or (w["gate"].get("first_review") is None and w["gate"]["attempts"] == 1 and w["gate"]["review"] == "PASS"))),
        "mut_listed": sum(w["gate"].get("mutation", {}).get("listed", 0) for w in wps),
        "mut_survived": sum(w["gate"].get("mutation", {}).get("survived", 0) for w in wps),
        "gate_noreview": sum(1 for w in wps if w["stages"]["verify"] == "done" and str(w["gate"].get("review", "")).lower() in ("none", "")),
        "cards_open": sum(1 for c in cards if c.get("status") == "OPEN"),
        "cards_auto": sum(1 for c in cards if c.get("status") == "AUTO-DECIDED"),
        "cards_total": len(cards),
        "open_blocking": sum(1 for g in open_gaps if g.get("severity") == "Blocking"),
        "open_high": sum(1 for g in open_gaps if g.get("severity") == "High"),
        "open_low": sum(1 for g in open_gaps if g.get("severity") == "Low"),
        "answered": len(gaps) - len(open_gaps),
        "drifts_open": sum(1 for d in cfg["drifts"] if not d.get("decision")),
        "ac_total": sum(w.get("ac_total", 0) for w in wps),
        "ac_tested": sum(w.get("ac_tested", 0) for w in wps),
    }
    cs = cfg["citation_samples"]
    s["hit_rate"] = f'{cs[-1].get("hits", 0)}/{cs[-1].get("sampled", 0)} ({cs[-1].get("date", "")})' if cs else "not run yet"
    return s


def phase_status(cfg, pid):
    if pid in RUN_PHASES:
        return cfg["phase_status"][pid]
    stage = next(s for s, p in STAGE_TO_PHASE.items() if p == pid)
    vals = [w["stages"][stage] for w in cfg["work_packages"]]
    if not vals: return "pending"
    if any(v == "blocked" for v in vals): return "blocked"
    if all(v == "done" for v in vals): return "done"
    return "in_progress" if any(v != "pending" for v in vals) else "pending"


# ---------------------------------------------------------------- Markdown
def md_tracker(cfg):
    s = summarise(cfg); mode = "Fully Automated" if cfg["mode"] == "automated" else "User Monitored"
    o = []; w = o.append
    w(f"# Execution Tracker — {cfg['task']}\n")
    w(f"> **Next action:** {cfg['next_action']}\n")
    w("## Run configuration\n")
    w("| Key | Value |\n|---|---|")
    w(f"| Mode | {mode} |"); w(f"| Output format | {cfg['format'].upper()} |"); w(f"| Output location | `{cfg['output_dir']}` |")
    w(f"| Target access | {cfg.get('target', '—')} |"); w(f"| Started | {cfg['started']} |")
    w(f"| Built against | {cfg.get('spec_ref', '— (record in Phase 0)')} |"); w(f"| Budget | {cfg.get('budget', '—')} |")
    w(f"| Cost profile | {PROFILES[cfg['cost_profile']]} |")
    w(f"| Fidelity | {FIDELITY[cfg['fidelity']]} |")
    w(f"| Effort | " + " · ".join(f"{lbl}: {EFFORT[cfg['effort'][k]]}" for k, lbl in EFFORT_DIMS) + " |")
    w(f"| Stack | {', '.join(cfg['stack']) or '— (not a coding task, or not yet confirmed)'} |")
    w(f"| Summary sources | {', '.join(cfg['summary_sources']) or '—'} |")
    w(f"| Tooling | {'Claude only' if cfg['tooling'] == 'claude-only' else str(len(cfg['tooling'])) + ' tool(s) — see below'} |")
    w(f"| Reviewer effort | {REVIEW[cfg['review_depth']]} |")
    w(f"| Build self-check | {SELFCHECK[cfg['self_check']]} |")
    w(f"| Test budget | {cfg['test_budget']} (derived from fidelity + logic effort; exceeding raises a Decision Card) |")
    w(f"| Call budget per stage | " + " · ".join(f"{k} {v}" for k, v in cfg['budget_calls'].items()) + " (cap hit → clean handoff + Decision Card) |")
    w(f"| Review lenses | {', '.join(l['id'] for l in cfg['lenses'])} |\n")
    if cfg.get("summary"): w(f"**Owner summary (intent, not evidence):** {cfg['summary']}\n")
    if cfg.get("goal"): w(f"**Goal:** {cfg['goal']}\n")
    if cfg["expected_output"]:
        w("**Expected output**\n"); w("| Artefact | Where | Checked by |\n|---|---|---|")
        for e in cfg["expected_output"]: w(f"| {e.get('artefact','')} | {e.get('where','')} | {e.get('check','')} |")
        w("")
    if cfg["tooling"] != "claude-only":
        w("**Tooling plan**\n"); w("| Tool | Used for | WPs | Availability | Produces |\n|---|---|---|---|---|")
        for t in cfg["tooling"]: w(f"| {t.get('tool','')} | {t.get('used_for','')} | {', '.join(t.get('wps', []))} | {t.get('availability','')} | {t.get('produces','')} |")
        w("")
    for title, key in (("Definition of done", "definition_of_done"), ("Locked decisions", "locked_decisions"), ("Non-goals", "non_goals")):
        if cfg[key]:
            w(f"**{title}**\n"); [w(f"{i}. {x}") for i, x in enumerate(cfg[key], 1)]; w("")
    w("**Decision rules (unattended)**\n"); [w(f"{i}. {r}") for i, r in enumerate(cfg["decision_rules"], 1)]; w("")
    w("## At a glance\n")
    w(f"- Work packages: {s['wps_done']}/{s['wps']} complete · {s['wps_blocked']} BLOCKED · gates passed {s['gate_passed']} over {s['gate_attempts']} attempts" + (f" · **{s['gate_noreview']} passed without independent review**" if s['gate_noreview'] else ""))
    w(f"- Acceptance criteria tested: {s['ac_tested']}/{s['ac_total']}")
    w(f"- Tool calls logged: {s['calls_total']} · cap hits: {s['cap_hits']}")
    if s["review_first_avg"] or s["review_re_avg"]:
        w(f"- Review cost: first reviews avg {s['review_first_avg']:,} tok · re-reviews avg {s['review_re_avg']:,} tok ({s['re_scoped']} scoped / {s['re_full']} full) · fixes {s['fix_continued']} continued / {s['fix_fresh']} fresh")
    w(f"- First-review pass rate: {s['first_pass']}/{s['gated']}" + (f" · mutants listed {s['mut_listed']}, survived {s['mut_survived']}" if s['mut_listed'] else "") if s['gated'] else "- First-review pass rate: — (no gates yet)")
    w(f"- Decision cards: {s['cards_open']} open · {s['cards_auto']} auto-decided · {s['cards_total']} total")
    w(f"- Open gaps: {s['open_blocking']} Blocking · {s['open_high']} High · {s['open_low']} Low · {s['answered']} answered")
    w(f"- Drift undecided: {s['drifts_open']} · Citation hit rate: {s['hit_rate']}\n")
    w("## Phase plan, model & effort\n")
    w(f"Cost profile **{PROFILES[cfg['cost_profile']]}** — the orchestrator launches each stage's agent with the *resolved* model/effort; *used* comes from the session log. ⚑ = critical (floors at sonnet/medium under Very Low Budget; first up under I Am Too Rich).\n")
    w("| Phase | Scope | Recommended | Resolved (this profile) | Used | Status |\n|---|---|---|---|---|---|")
    used = used_models(cfg)
    for pid, name, scope in PHASES:
        m = cfg["models"][pid]; r = cfg["resolved_models"][pid]; st = phase_status(cfg, pid)
        crit = " ⚑" if m.get("critical") else ""; note = f" ({m['note']})" if m.get("note") else ""
        w(f"| {pid} — {name}{crit} | {scope} | {m['tier']} / {m['effort']}{note} | **{r['model']}** / {r['effort']} | {', '.join(used.get(pid, [])) or '—'} | {MARK.get(st, '')} {st} |")
        if pid == "3":
            mf = cfg["models"]["3fix"]; rf = cfg["resolved_models"]["3fix"]
            w(f"| 3 — fix loop | per failed gate | {mf['tier']} / {mf['effort']} | **{rf['model']}** / {rf['effort']} | {', '.join(used.get('3fix', [])) or '—'} | — |")
            mr = cfg["models"]["3re"]; rr = cfg["resolved_models"]["3re"]
            w(f"| 3 — scoped re-review | per fix loop | {mr['tier']} / {mr['effort']} ({mr.get('note','')}) | **{rr['model']}** / {rr['effort']} | {', '.join(used.get('3re', [])) or '—'} | — |")
    w("")
    w("## Work package × stage matrix\n")
    if not cfg["work_packages"]:
        w("_No work packages yet — Phase 0 proposes them and DC-000 approves them._")
    else:
        w("| WP | Name | Depends on | Design | Build | Verify | Integrate | Gate (attempts / fix loops) | AC tested |\n|---|---|---|---|---|---|---|---|---|")
        for x in cfg["work_packages"]:
            g = x["gate"]
            mut = g.get("mutation") or {}
            gate = f"{'BLOCKED' if g['blocked'] else (g['review'] or '—')} ({g['attempts']} / {g['fix_loops']})" + (f" · 1st {g['first_review']}" if g.get("first_review") else "") + (f" · mut {mut.get('listed',0)}/{mut.get('survived',0)}" if mut else "")
            cells = " | ".join(f"{MARK.get(x['stages'][st], '')} {x['stages'][st]}" for st, _ in STAGES)
            w(f"| {'★ ' if x['pilot'] else ''}{x['id']} | {x['name']} | {', '.join(x['depends_on']) or '—'} | {cells} | {gate} | {x.get('ac_tested', 0)}/{x.get('ac_total', 0)} |")
        w("\n★ = pilot work package (runs Design → Build → Verify → Card before any other).")
    w("")
    w("## Decision cards\n")
    if not cfg["decision_cards"]:
        w("_None raised yet. DC-000 is raised at the end of Phase 0._")
    else:
        w("| Id | Title | WP | Between | Status | Stops run | Decision | By / rule | Date |\n|---|---|---|---|---|---|---|---|---|")
        for c in cfg["decision_cards"]:
            by = c.get("by") or (f"AUTO rule {c['rule']}" if c.get("rule") else "—")
            w(f"| {c.get('id','')} | {c.get('title','')} | {c.get('wp','') or '—'} | {c.get('between','')} | {c.get('status','')} | "
              f"{'yes' if c.get('stops_run') else 'no'} | {c.get('decision') or '—'} | {by} | {c.get('date','')} |")
    w("")
    w("## ADR log\n")
    if not cfg["adrs"]: w("_No ADRs yet._")
    else:
        w("| Id | Title | Status | Decided via |\n|---|---|---|---|")
        for a in cfg["adrs"]: w(f"| {a.get('id','')} | {a.get('title','')} | {a.get('status','')} | {a.get('dc') or '—'} |")
    w("")
    w("## GAP log\n")
    if not cfg["gaps"]: w("_No gaps logged yet._")
    else:
        w("| Id | Severity | Description | Found in | Blocks | Question | Answered |\n|---|---|---|---|---|---|---|")
        order = {"Blocking": 0, "High": 1, "Low": 2}
        for g in sorted(cfg["gaps"], key=lambda g: (bool(g.get("answered")), order.get(g.get("severity"), 3), g.get("id", ""))):
            w(f"| {g.get('id','')} | {g.get('severity','')} | {g.get('desc','')} | {g.get('found_in','')} | {g.get('blocks','')} | {g.get('question','')} | {g.get('answered') or '—'} |")
    w("")
    w("## DRIFT log\n")
    if not cfg["drifts"]: w("_No drift logged yet._")
    else:
        w("| Id | Description | Side A | Side B | Protected | Decision |\n|---|---|---|---|---|---|")
        for d in cfg["drifts"]:
            w(f"| {d.get('id','')} | {d.get('desc','')} | {d.get('side_a','')} | {d.get('side_b','')} | {'yes' if d.get('protected') else 'no'} | {d.get('decision') or '— pending'} |")
    w("")
    w("## Risk register\n")
    if not cfg["risks"]: w("_No risks recorded._")
    else:
        w("| Id | Risk | L / I | Trigger | Mitigation | Owner |\n|---|---|---|---|---|---|")
        for r in cfg["risks"]:
            w(f"| {r.get('id','')} | {r.get('risk','')} | {r.get('likelihood','')} / {r.get('impact','')} | {r.get('trigger','')} | {r.get('mitigation','')} | {r.get('owner','')} |")
    w("")
    w("## Citation-sample checks (Phase 5)\n")
    if not cfg["citation_samples"]: w("_Not run yet._")
    else:
        w("| Date | Scope | Sampled | Hits | Misses |\n|---|---|---|---|---|")
        for c in cfg["citation_samples"]:
            w(f"| {c.get('date','')} | {c.get('scope','')} | {c.get('sampled','')} | {c.get('hits','')} | {'; '.join(c.get('misses', [])) or '—'} |")
    w("")
    w("## Delta rounds\n")
    if not cfg["delta_rounds"]: w("_None yet. Run one when the spec or inputs change (playbook-core §9.3)._")
    else:
        w("| Date | From | To | Stale | Re-designed | Re-gated | Notes |\n|---|---|---|---|---|---|---|")
        for r in cfg["delta_rounds"]:
            w(f"| {r.get('date','')} | {r.get('from_ref','')} | {r.get('to_ref','')} | {r.get('stale','')} | {r.get('redesigned','')} | {r.get('regated','')} | {r.get('notes','')} |")
    w("")
    w("## Session log\n")
    if not cfg["sessions"]: w("_No sessions recorded._")
    else:
        w("| Date | Phase | WP | Model | Calls / cap | Tokens | Notes |\n|---|---|---|---|---|---|---|")
        for x in cfg["sessions"]:
            calls = f"{x['calls']} / {x.get('cap','—')}" + (" ⛔" if x.get("cap") and x["calls"] >= x["cap"] else "") if x.get("calls") is not None else "—"
            extra = " ".join(filter(None, [f"att {x['attempt']}" if x.get("attempt") else "", x.get("scope", ""), f"fix: {x['fix']}" if x.get("fix") else ""]))
            w(f"| {x.get('date','')} | {x.get('phase','')} | {x.get('wp','') or '—'} | {x.get('model','')} | {calls} | {x.get('tokens') or '—'} | {(extra + ' · ') if extra else ''}{x.get('notes','')} |")
    w("\n---")
    w(f"_Generated by build_tracker.py from `run-config.json` on {date.today().isoformat()}. Edit the config, not this file._")
    return "\n".join(o)


def md_usage(cfg):
    mode = cfg["mode"]; lenses = ", ".join(l["id"] for l in cfg["lenses"])
    fid_line = {"poc": "Happy scenario only, cheapest technology and simplest design; everything skipped is listed as [PLANNED] in PLAYBOOK.md. Not a product.",
                "mvp": "A working vertical slice with good architecture and the main validations; what is outside the slice is [PLANNED].",
                "full": "Ready and tested, best approaches, non-functional criteria included."}[cfg["fidelity"]]
    eff_line = " · ".join(f"{lbl} {EFFORT[cfg['effort'][k]]}" for k, lbl in EFFORT_DIMS)
    tool_line = "Claude only" if cfg["tooling"] == "claude-only" else ", ".join(t.get("tool", "") for t in cfg["tooling"])
    sc_line = {"minimal": "Build self-check Minimal: fail-first evidence only.", "standard": "Build self-check Standard: every conditional, boundary, fallback and cap the WP added was mutated and the survivors got tests; the mutation table is in the WP file and the reviewer re-applied three.", "tool": "Build self-check Tool-backed: the mutation sweep plus a mutation-testing tool per gate on the changed files."}[cfg["self_check"]]
    rev_line = {"none": "No independent review — gates are commands + self-check; the tracker marks every such gate.",
                "low": "Reviewer effort Low — the reviewer sees ACs, diff and gate output only.",
                "medium": "Reviewer effort Medium — the reviewer is briefed with a context pack (shared cached block + the WP's contracts, ADRs, diff, hints, read list).",
                "high": "Reviewer effort High — the reviewer reads the whole playbook folder and repository."}[cfg["review_depth"]]
    out = f"""# How to use the {cfg['task']} execution run

**Fidelity: {FIDELITY[cfg['fidelity']]}.** {fid_line} Effort: {eff_line}. Tooling: {tool_line}. {rev_line} {sc_line} Test budget: {cfg['test_budget']}.

**What this is.** The task is cut into work packages. Each one is designed, built tests-first, then verified by gate commands and an adversarial review in a fresh context. Between phases a Decision Card shows what was done, the evidence, the options and a recommendation — you (or, unattended, a fixed rule set) decide. Everything is recorded in `{cfg['output_dir']}`.

## Where to look

- `TRACKER.md` / `.html` — where the run is: the work-package matrix, gate results, Decision Cards, ADRs, gaps, drift, risks. Start at **Next action**.
- `PLAYBOOK.md` — goal, definition of done, locked decisions, non-goals, the work-package breakdown.
- `work-packages/WP-NN-*.md` — one per package: acceptance criteria `AC-##`, test list, gate commands, build note, gate history.
- `decisions/DC-###.md` — the Decision Cards. `DECISIONS.md` is the one-line-per-decision index.
- `adr/ADR-###.md` — why a technical choice was made. `review/WP-NN-review.md` — what the reviewer found, per attempt.
- `GAPS.md` / `RISKS.md` — what is unknown, and what could go wrong.

## How to read a tag

- `[src: File#Member]` / `[src: SPEC §n]` — the claim is backed there. Open it before relying on it.
- `[GAP-###]` — a needed fact nobody had. Nothing was guessed; the question is in GAPS.md.
- `[DRIFT-###]` — two sources disagree; both sides shown; a decision is pending.
- `[PLANNED]` — deferred to a named later package, on purpose.
- `[UNTESTED: AC-##]` / `[tested: …]` — whether a criterion has a passing test. An untested AC fails the gate unless planned.
- `[ADR-###]` / `[DC-###]` — a recorded decision; `[DC-### AUTO rule n]` means a rule decided it unattended.
- `[RISK-###]`, `[STALE]` (source changed since written), `[BLOCKED]` (gate failed twice; run stopped here).

## Answering a Decision Card

One line: `DC-007: B — keep the dispatcher hand-rolled; revisit if the contract set grows`. Several at once is fine. The run applies them in id order, updates `DECISIONS.md`, and continues from the card's next phase.

## Unblocking a BLOCKED package

Read its card (the findings are on it) and `review/WP-NN-review.md`. Give the missing input, accept a `[GAP]`, or change the acceptance criteria through an ADR. The fix counter resets and the package re-enters its fix session; a gate is never loosened to get past it.

## When the spec changes

Ask for a **delta round**: it diffs the spec, marks affected criteria `[STALE]`, re-designs only those packages, and re-runs gates on them and everything downstream. Decisions and answers are kept.

## Execution mode: {"Fully Automated" if mode == "automated" else "User Monitored"}

"""
    if mode == "automated":
        out += """The run proceeds without you. Decision Cards are resolved by the decision rules and marked `AUTO-DECIDED` with the rule used; the final audit lists every one for your re-check. The run stops and waits only for a BLOCKED package, an irreversible action, a budget overrun, or drift touching a protected rule. To switch to User Monitored, say so — the next card waits for you.
"""
    else:
        out += """You manage prompt execution. At each phase boundary the tracker's **Next action** names the prompt or the card; the prepared prompt runs on your go — or you run it in your own Claude session and report back. The run waits at every Decision Card. To switch to Fully Automated, say so; it continues from the current next action under the decision rules.
"""
    out += f"\n## Review lenses in force\n\n{lenses} — each finding in a review names the lens that raised it, so a card shows which perspective objected.\n"
    res = cfg["resolved_models"]
    out += f"""
## Cost profile: {PROFILES[cfg['cost_profile']]}

Each stage runs on the model and effort the playbook recommends for it, shifted by this profile; the orchestrator launches a separate agent per stage with that model. This run: {', '.join(f'{pid} → {res[pid]["model"]}/{res[pid]["effort"]}' for pid in ("0", "1", "2", "3", "3fix", "4", "5", "6"))}. The tracker shows recommended, resolved and actually-used side by side. If a stage spends more than twice its budget, a Decision Card is raised whatever the mode. To change the profile for stages not yet started, say so — it is recorded as a decision.
"""
    return out


# ---------------------------------------------------------------- HTML
CSS = """
:root{--bg:#12151C;--surface:#1B212C;--surface-2:#212837;--border:#2A3140;--text:#E8EAED;--text-2:#96A0B3;--text-3:#5A6272;
--teal:#4FD1C5;--teal-dim:rgba(79,209,197,.12);--amber:#E8A33D;--amber-dim:rgba(232,163,61,.12);--coral:#E8735C;--coral-dim:rgba(232,115,92,.14);
--blue:#7C9CE8;--blue-dim:rgba(124,156,232,.12);--violet:#B48EE8;--sans:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;--mono:'IBM Plex Mono',SF Mono,Consolas,monospace}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F7F9;--surface:#fff;--surface-2:#EEF1F5;--border:#D9DEE6;--text:#1B2230;--text-2:#4B5565;--text-3:#8A93A3;--teal:#0E8F84;--teal-dim:rgba(14,143,132,.1);--amber:#B86E0A;--amber-dim:rgba(184,110,10,.1);--coral:#C4462C;--coral-dim:rgba(196,70,44,.1);--blue:#3A5BC7;--blue-dim:rgba(58,91,199,.1);--violet:#7A4FC7}}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14.5px;line-height:1.6}
.wrap{max-width:1240px;margin:0 auto;padding:32px 16px 96px}h1{font-size:26px;margin-bottom:6px}h2{font-size:18px;margin:36px 0 10px;display:flex;align-items:center;gap:10px}
h2 .n{font-family:var(--mono);color:var(--text-3);font-size:13px;font-weight:500}.sub{color:var(--text-2);font-size:13.5px;margin-bottom:14px}
.next{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--teal);border-radius:8px;padding:14px 18px;margin:18px 0 8px}
.next b{color:var(--teal);font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;display:block;margin-bottom:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:14px 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}.card .k{font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:.07em}
.card .v{font-size:20px;font-weight:600;margin-top:4px}.card .v.warn{color:var(--coral)}.card .v.ok{color:var(--teal)}.card .v.amber{color:var(--amber)}
.tbl{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--surface)}table{width:100%;border-collapse:collapse;font-size:13.2px}
th{text-align:left;background:var(--surface-2);color:var(--text-3);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:10px 12px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid var(--border);color:var(--text-2);vertical-align:top}tr:last-child td{border-bottom:none}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-2);white-space:nowrap}
.pill.done{color:var(--teal);background:var(--teal-dim);border-color:var(--teal)}.pill.in_progress{color:var(--amber);background:var(--amber-dim);border-color:var(--amber)}
.pill.blocked{color:var(--coral);background:var(--coral-dim);border-color:var(--coral)}.pill.skipped{opacity:.5}.pill.click{cursor:pointer}
.pill.OPEN{color:var(--amber);border-color:var(--amber);background:var(--amber-dim)}.pill.DECIDED{color:var(--teal);border-color:var(--teal);background:var(--teal-dim)}
.pill.AUTO-DECIDED{color:var(--blue);border-color:var(--blue);background:var(--blue-dim)}.pill.SUPERSEDED{opacity:.5}
.pill.PASS{color:var(--teal);border-color:var(--teal)}.pill.FAIL{color:var(--coral);border-color:var(--coral)}.pill.BLOCKED{color:var(--coral);border-color:var(--coral);background:var(--coral-dim);font-weight:600}
.sev-Blocking{color:var(--coral);font-weight:600}.sev-High{color:var(--amber);font-weight:600}.sev-Low{color:var(--text-3)}
code{font-family:var(--mono);font-size:12.3px;background:var(--surface-2);padding:1px 5px;border-radius:4px}.muted{color:var(--text-3);font-size:13px}
.star{color:var(--amber)}footer{margin-top:40px;color:var(--text-3);font-size:12px}.kv td:first-child{color:var(--text-3);white-space:nowrap;width:180px}
ol,ul{padding-left:22px;color:var(--text-2)}li{margin:4px 0}p{color:var(--text-2);margin:8px 0}.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.box{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}.box h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin-bottom:8px}
"""


def esc(x): return html.escape(str(x if x is not None else ""))
def pill(st, extra=""): return f'<span class="pill {esc(st)} {extra}">{MARK.get(st, "")} {esc(st)}</span>'


def shell(title, body, js=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">{body}</div><script>{js}</script></body></html>"""


def table(headers, rows):
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl"><table><tr>{h}</tr>{b}</table></div>'


def html_tracker(cfg):
    s = summarise(cfg); mode = "Fully Automated" if cfg["mode"] == "automated" else "User Monitored"
    o = []; w = o.append
    w(f"<h1>Execution Tracker — {esc(cfg['task'])}</h1>")
    w(f'<div class="sub">{mode} · {esc(cfg["format"].upper())} · started {esc(cfg["started"])} · built against {esc(cfg.get("spec_ref") or "— (set in Phase 0)")}</div>')
    w(f'<div class="next"><b>Next action</b>{esc(cfg["next_action"])}</div>')
    w('<div class="grid">')
    w(f'<div class="card"><div class="k">Work packages</div><div class="v">{s["wps_done"]}/{s["wps"]} <span class="muted">{"· " + str(s["wps_blocked"]) + " blocked" if s["wps_blocked"] else ""}</span></div></div>')
    w(f'<div class="card"><div class="k">Gates passed / attempts</div><div class="v">{s["gate_passed"]} / {s["gate_attempts"]}' + (f' <span class="muted" style="color:var(--coral)">({s["gate_noreview"]} no review)</span>' if s["gate_noreview"] else "") + '</div></div>')
    w(f'<div class="card"><div class="k">AC tested</div><div class="v">{s["ac_tested"]}/{s["ac_total"]}</div></div>')
    w(f'<div class="card"><div class="k">Calls · cap hits</div><div class="v {"warn" if s["cap_hits"] else ""}">{s["calls_total"]} · {s["cap_hits"]}</div></div>')
    if s["review_first_avg"] or s["review_re_avg"]:
        w(f'<div class="card"><div class="k">Review tokens first → re</div><div class="v">{s["review_first_avg"]//1000}k → {s["review_re_avg"]//1000}k <span class="muted">{s["re_scoped"]} scoped / {s["re_full"]} full</span></div></div>')
    w(f'<div class="card"><div class="k">First-review pass</div><div class="v {"ok" if s["gated"] and s["first_pass"] == s["gated"] else ("amber" if s["gated"] else "")}">{s["first_pass"]}/{s["gated"] or "—"}' + (f' <span class="muted">mut {s["mut_listed"]}/{s["mut_survived"]}</span>' if s["mut_listed"] else "") + '</div></div>')
    w(f'<div class="card"><div class="k">Decision cards open</div><div class="v {"amber" if s["cards_open"] else "ok"}">{s["cards_open"]} <span class="muted">· {s["cards_auto"]} auto</span></div></div>')
    w(f'<div class="card"><div class="k">Open Blocking / High</div><div class="v {"warn" if s["open_blocking"] or s["open_high"] else "ok"}">{s["open_blocking"]} / {s["open_high"]}</div></div>')
    w(f'<div class="card"><div class="k">Citation hit rate</div><div class="v">{esc(s["hit_rate"])}</div></div>')
    w('</div>')

    w('<h2><span class="n">01</span>Run configuration</h2><div class="tbl"><table class="kv">')
    rows = [("Mode", mode), ("Output format", cfg["format"].upper()), ("Output location", f"<code>{esc(cfg['output_dir'])}</code>"),
            ("Target access", esc(cfg.get("target", "—"))), ("Budget", esc(cfg.get("budget", "—"))),
            ("Cost profile", f'<span class="pill in_progress">{esc(PROFILES[cfg["cost_profile"]])}</span>'),
            ("Fidelity", f'<span class="pill done">{esc(FIDELITY[cfg["fidelity"]])}</span>'),
            ("Effort", " ".join(f'<span class="pill">{esc(lbl)}: {esc(EFFORT[cfg["effort"][k]])}</span>' for k, lbl in EFFORT_DIMS)),
            ("Stack", esc(", ".join(cfg["stack"]) or "— (not a coding task, or not yet confirmed)")),
            ("Summary sources", esc(", ".join(cfg["summary_sources"]) or "—")),
            ("Tooling", "Claude only" if cfg["tooling"] == "claude-only" else f"{len(cfg['tooling'])} tool(s) — see below"),
            ("Reviewer effort", f'<span class="pill {"blocked" if cfg["review_depth"] == "none" else "in_progress"}">{esc(REVIEW[cfg["review_depth"]])}</span>'),
            ("Build self-check", f'<span class="pill {"in_progress" if cfg["self_check"] == "minimal" else "done"}">{esc(SELFCHECK[cfg["self_check"]])}</span>'),
            ("Test budget", esc(cfg["test_budget"]) + ' <span class="muted">(derived; exceeding raises a Decision Card)</span>'),
            ("Call budget per stage", " ".join(f'<span class="pill">{esc(k)} {v}</span>' for k, v in cfg["budget_calls"].items()) + ' <span class="muted">cap hit → clean handoff + Decision Card</span>'),
            ("Review lenses", " ".join(f'<span class="pill">{esc(l["id"])}</span>' for l in cfg["lenses"]))]
    if cfg.get("summary"): rows.append(("Owner summary", esc(cfg["summary"]) + ' <span class="muted">(intent, not evidence)</span>'))
    if cfg.get("goal"): rows.append(("Goal", esc(cfg["goal"])))
    for k, v in rows: w(f"<tr><td>{k}</td><td>{v}</td></tr>")
    w("</table></div>")
    if cfg["expected_output"]:
        w('<h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin:14px 0 6px">Expected output</h3>')
        w(table(["Artefact", "Where", "Checked by"], [[esc(e.get("artefact")), esc(e.get("where")), esc(e.get("check"))] for e in cfg["expected_output"]]))
    if cfg["tooling"] != "claude-only":
        w('<h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin:14px 0 6px">Tooling plan</h3>')
        w(table(["Tool", "Used for", "WPs", "Availability", "Produces"], [[esc(t.get("tool")), esc(t.get("used_for")), esc(", ".join(t.get("wps", []))),
          f"<span class='pill {'done' if t.get('availability') == 'available' else 'in_progress' if str(t.get('availability','')).startswith('needs') else 'blocked'}'>{esc(t.get('availability'))}</span>", esc(t.get("produces"))] for t in cfg["tooling"]]))
    w('<div class="cols" style="margin-top:14px">')
    for title, key in (("Definition of done", "definition_of_done"), ("Locked decisions", "locked_decisions"), ("Non-goals", "non_goals"), ("Decision rules (unattended)", "decision_rules")):
        items = cfg[key]
        w(f'<div class="box"><h3>{title}</h3>' + ("<ol>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ol>" if items else '<p class="muted">— (Phase 0)</p>') + "</div>")
    w("</div>")

    w('<h2><span class="n">02</span>Phase plan, model &amp; effort</h2>')
    w(f'<div class="sub">Cost profile <b>{esc(PROFILES[cfg["cost_profile"]])}</b> — the orchestrator launches each stage\'s agent with the <i>resolved</i> model/effort; <i>used</i> comes from the session log. ⚑ critical phase.</div>')
    used = used_models(cfg); prow = []
    def mrow(pid, label, scope, st_html):
        m = cfg["models"][pid]; r = cfg["resolved_models"][pid]
        crit = ' <span class="star">⚑</span>' if m.get("critical") else ""; note = f' <span class="muted">({esc(m["note"])})</span>' if m.get("note") else ""
        return [f"{label}{crit}", esc(scope), f"{esc(m['tier'])} / {esc(m['effort'])}{note}",
                f"<span class='pill done'>{esc(r['model'])}</span> <span class='pill'>{esc(r['effort'])}</span>", esc(", ".join(used.get(pid, [])) or "—"), st_html]
    for pid, n, sc in PHASES:
        prow.append(mrow(pid, f"<b>{pid}</b> — {esc(n)}", sc, pill(phase_status(cfg, pid))))
        if pid == "3":
            prow.append(mrow("3fix", "<b>3</b> — fix loop", "per failed gate", "—"))
            prow.append(mrow("3re", "<b>3</b> — scoped re-review", "per fix loop", "—"))
    w(table(["Phase", "Scope", "Recommended", "Resolved", "Used", "Status"], prow))

    w('<h2><span class="n">03</span>Work package × stage matrix</h2>')
    if not cfg["work_packages"]:
        w('<p class="muted">No work packages yet — Phase 0 proposes them and DC-000 approves them.</p>')
    else:
        w('<div class="sub">Click a stage cell to cycle its status locally (remembered in this browser only; the config is updated at the next checkpoint).</div>')
        rows = []
        for i, x in enumerate(cfg["work_packages"]):
            g = x["gate"]
            gate = pill("BLOCKED") if g["blocked"] else (pill(g["review"]) if g["review"] else "—")
            mut = g.get("mutation") or {}
            if g.get("first_review"): gate += f" <span class='muted'>1st {esc(g['first_review'])}</span>"
            if mut: gate += f" <span class='muted'>mut {mut.get('listed',0)}/{mut.get('survived',0)}</span>"
            cells = [f'<span class="pill click {x["stages"][st]}" data-wp="{i}" data-stage="{st}">{MARK.get(x["stages"][st], "")} {x["stages"][st]}</span>' for st, _ in STAGES]
            rows.append([('<span class="star">★</span> ' if x["pilot"] else "") + f"<b>{esc(x['id'])}</b>", esc(x["name"]), esc(", ".join(x["depends_on"]) or "—"),
                         *cells, f"{gate} <span class='muted'>{g['attempts']} att · {g['fix_loops']} fix</span>", f"{x.get('ac_tested', 0)}/{x.get('ac_total', 0)}"])
        w(table(["WP", "Name", "Depends on", "Design", "Build", "Verify", "Integrate", "Gate", "AC tested"], rows))
        w("<p class='muted'>★ pilot work package — runs Design → Build → Verify → Card before any other.</p>")

    w('<h2><span class="n">04</span>Decision cards</h2>')
    if not cfg["decision_cards"]:
        w('<p class="muted">None raised yet. DC-000 is raised at the end of Phase 0.</p>')
    else:
        rows = []
        for c in cfg["decision_cards"]:
            by = esc(c.get("by")) or (f"AUTO rule {esc(c['rule'])}" if c.get("rule") else "—")
            link = f'<a href="decisions/{esc(c.get("id"))}.html" style="color:var(--teal)">{esc(c.get("id"))}</a>'
            rows.append([link, esc(c.get("title")), esc(c.get("wp") or "—"), esc(c.get("between")), pill(c.get("status", "")),
                         '<span class="sev-Blocking">yes</span>' if c.get("stops_run") else "no", esc(c.get("decision") or "—"), by, esc(c.get("date"))])
        w(table(["Id", "Title", "WP", "Between", "Status", "Stops run", "Decision", "By / rule", "Date"], rows))

    w('<h2><span class="n">05</span>ADR log</h2>')
    w(table(["Id", "Title", "Status", "Decided via"], [[esc(a.get("id")), esc(a.get("title")), esc(a.get("status")), esc(a.get("dc") or "—")] for a in cfg["adrs"]]) if cfg["adrs"] else '<p class="muted">No ADRs yet.</p>')

    w('<h2><span class="n">06</span>GAP log</h2>')
    if cfg["gaps"]:
        order = {"Blocking": 0, "High": 1, "Low": 2}
        gs = sorted(cfg["gaps"], key=lambda g: (bool(g.get("answered")), order.get(g.get("severity"), 3), g.get("id", "")))
        w(table(["Id", "Sev", "Description", "Found in", "Blocks", "Question", "Answered"],
                [[f"<code>{esc(g.get('id'))}</code>", f"<span class='sev-{esc(g.get('severity'))}'>{esc(g.get('severity'))}</span>", esc(g.get("desc")), esc(g.get("found_in")), esc(g.get("blocks")), esc(g.get("question")), esc(g.get("answered") or "—")] for g in gs]))
    else: w('<p class="muted">No gaps logged yet.</p>')

    w('<h2><span class="n">07</span>DRIFT log</h2>')
    w(table(["Id", "Description", "Side A", "Side B", "Protected", "Decision"],
            [[f"<code>{esc(d.get('id'))}</code>", esc(d.get("desc")), esc(d.get("side_a")), esc(d.get("side_b")), '<span class="sev-High">yes</span>' if d.get("protected") else "no", esc(d.get("decision") or "— pending")] for d in cfg["drifts"]]) if cfg["drifts"] else '<p class="muted">No drift logged yet.</p>')

    w('<h2><span class="n">08</span>Risk register</h2>')
    w(table(["Id", "Risk", "L / I", "Trigger", "Mitigation", "Owner"],
            [[f"<code>{esc(r.get('id'))}</code>", esc(r.get("risk")), f"{esc(r.get('likelihood'))} / {esc(r.get('impact'))}", esc(r.get("trigger")), esc(r.get("mitigation")), esc(r.get("owner"))] for r in cfg["risks"]]) if cfg["risks"] else '<p class="muted">No risks recorded.</p>')

    w('<h2><span class="n">09</span>Citation-sample checks</h2>')
    w(table(["Date", "Scope", "Sampled", "Hits", "Misses"], [[esc(c.get("date")), esc(c.get("scope")), esc(c.get("sampled")), esc(c.get("hits")), esc("; ".join(c.get("misses", [])) or "—")] for c in cfg["citation_samples"]]) if cfg["citation_samples"] else '<p class="muted">Not run yet (Phase 5).</p>')

    w('<h2><span class="n">10</span>Delta rounds</h2>')
    w(table(["Date", "From", "To", "Stale", "Re-designed", "Re-gated", "Notes"], [[esc(r.get(k)) for k in ("date", "from_ref", "to_ref", "stale", "redesigned", "regated", "notes")] for r in cfg["delta_rounds"]]) if cfg["delta_rounds"] else '<p class="muted">None yet. Run one when the spec or inputs change.</p>')

    w('<h2><span class="n">11</span>Session log</h2>')
    w(table(["Date", "Phase", "WP", "Model", "Notes"], [[esc(x.get("date")), esc(x.get("phase")), esc(x.get("wp") or "—"), esc(x.get("model")), esc(x.get("notes"))] for x in cfg["sessions"]]) if cfg["sessions"] else '<p class="muted">No sessions recorded.</p>')
    w(f"<footer>Generated by build_tracker.py from <code>run-config.json</code> on {date.today().isoformat()}. Edit the config, not this file.</footer>")

    js = f"""
(function(){{
  var KEY='exec-tracker:{esc(cfg["task"])}', ORDER=['pending','in_progress','done','blocked'], MARK={json.dumps(MARK)};
  var saved={{}}; try{{saved=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
  function key(el){{return el.dataset.wp+':'+el.dataset.stage}}
  function apply(el,st){{el.className='pill click '+st; el.textContent=(MARK[st]||'')+' '+st}}
  document.querySelectorAll('.pill.click').forEach(function(el){{
    var k=key(el); if(saved[k]) apply(el,saved[k]);
    el.addEventListener('click',function(){{
      var cur=ORDER.indexOf((el.className.match(/pending|in_progress|done|blocked/)||['pending'])[0]);
      var nxt=ORDER[(cur+1)%ORDER.length]; apply(el,nxt); saved[k]=nxt;
      try{{localStorage.setItem(KEY,JSON.stringify(saved))}}catch(e){{}}
    }});
  }});
}})();"""
    return shell(f"Tracker — {cfg['task']}", "".join(o), js)


def html_usage(cfg):
    import re
    md = md_usage(cfg); out, in_list = [], False
    def inline(t):
        t = esc(t); t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t); return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    for line in md.splitlines():
        if line.startswith("# "): out.append(f"<h1>{inline(line[2:])}</h1>"); continue
        if line.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h2>{inline(line[3:])}</h2>"); continue
        if line.startswith("- "):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(line[2:])}</li>"); continue
        if in_list and not line.strip(): out.append("</ul>"); in_list = False; continue
        if line.strip(): out.append(f"<p>{inline(line)}</p>")
    if in_list: out.append("</ul>")
    return shell(f"Usage — {cfg['task']}", "".join(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config"); ap.add_argument("--out", default=None); ap.add_argument("--format", choices=["md", "html", "both"], default=None)
    a = ap.parse_args()
    cfg = load(a.config); fmt = a.format or cfg["format"]; out = a.out or cfg["output_dir"]
    os.makedirs(out, exist_ok=True); written = []
    if fmt in ("md", "both"):
        for name, content in (("TRACKER.md", md_tracker(cfg)), ("USAGE.md", md_usage(cfg))):
            p = os.path.join(out, name); open(p, "w", encoding="utf-8").write(content); written.append(p)
    if fmt in ("html", "both"):
        for name, content in (("TRACKER.html", html_tracker(cfg)), ("USAGE.html", html_usage(cfg))):
            p = os.path.join(out, name); open(p, "w", encoding="utf-8").write(content); written.append(p)
    s = summarise(cfg)
    print("wrote: " + ", ".join(written))
    print(f"WPs {s['wps_done']}/{s['wps']} ({s['wps_blocked']} blocked) · gates {s['gate_passed']}/{s['gate_attempts']} att · cards open {s['cards_open']} · gaps B{s['open_blocking']} H{s['open_high']} L{s['open_low']}")
    print(f"next: {cfg['next_action']}")


if __name__ == "__main__":
    main()
