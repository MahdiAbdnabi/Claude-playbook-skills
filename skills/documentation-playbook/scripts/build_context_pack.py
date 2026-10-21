#!/usr/bin/env python3
"""
build_context_pack.py — context packs for the documentation playbook (rules: references/audit-and-packs.md §2).
  packs/shared.md              immutable for the run, hashed; FIRST in every helper prompt (cache prefix)
  packs/<batch>-extractor.md   Phases 1–4 block for one batch
  packs/<batch>-auditor.md     Phase 5 block, sized by audit_depth (none|low|medium|high); built from the corpus + doc_check, never from the extractor's block
  --scoped                     after a failed audit: the previous misses + a fresh sample from changed sections; prints full_audit_required

Usage:
    python3 build_context_pack.py "<batch name>" --config docs/_playbook/run-config.json [--repo .] [--phase 1|2|3|4|5] [--level none|low|medium|high]
    python3 build_context_pack.py "<batch name>" --config ... --scoped --misses logs/audit-<n>-misses.json
Reads run-config.json, the corpus documents, diagrams/, the latest logs/check-<n>.json and logs/sample-<n>.json (run doc_check.py --sample first).
"""
import argparse, hashlib, json, os, re, subprocess, sys
from datetime import date

PRINCIPLES = """1. Cite or flag — every claim is [src], [PLANNED], [GAP] or [DRIFT]; nothing is invented to sound complete.
2. Ground truth once, lenses after — lenses point into the core and add no claims.
3. Protected invariants get the most scrutiny, not the least.
4. Documentation proves comprehension, not correctness — prefer [tested:] where it exists; say when it does not.
5. Pilot one bounded context before batching the rest.
6. Ask early, not silently — Blocking/High gaps become one-line questions at the phase checkpoint.
7. Gaps are truth — the [GAP] count is the honest maturity measure; lowering it by guessing falsifies it."""
TAGS = """[src: File.ext#Member]  ·  [GAP-###: q]  ·  [DRIFT-###: A vs B]  ·  [PLANNED]  ·  [PROTECTED]  ·  [UNTESTED: BR-###] / [tested: Class.Method]  ·  [STALE]  ·  [rule: TBD]
Prefer File#Member to File:line. External sources: [src: SPEC §n], [src: owner-answer GAP-###]."""
TAXONOMY = "01 IDX · 02 ARC · 03 DAT · 04 MOD · 05 API · 06 INT · 07 XCC · 08 CNV · 09 UXF · 10 FLW · 11 BRI · 12 TST · 13 OPS · 14 DEP — one file per type, extended batch by batch; header: System / Scope / Version / Authority / Maturity line."


def sh(cmd, cwd):
    try: return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60).stdout
    except Exception: return ""


def tokens(s): return len(s) // 4


def repo_map(repo):
    out = []
    try:
        for name in sorted(os.listdir(repo)):
            if name.startswith(".") or name in ("node_modules", "bin", "obj", "dist", "docs"): continue
            p = os.path.join(repo, name)
            out.append(f"- {name}/  ({sum(len(f) for _, _, f in os.walk(p))} files)" if os.path.isdir(p) else f"- {name}")
    except Exception: out.append("(repo not readable)")
    return "\n".join(out[:60])


def profile_line(cfg):
    d = {"full": "Full documentation", "30min": "30-minute version", "10min": "10-minute version"}.get(cfg.get("depth", "full"), "Full")
    c = {"docs+diagrams": "docs + diagrams", "docs": "docs only", "diagrams": "diagrams only"}.get(cfg.get("content", "docs+diagrams"))
    s = cfg.get("diagram_style", "static"); dd = cfg.get("diagram_depth", "design")
    return f"{d} · {c}" + (f" · {s} diagrams at {dd} depth" if c != "docs" and s != "none" else "")


DEFAULT_BUDGETS = {"10min": {"0": 12, "1": 15, "2": 12, "3": 0, "4": 6, "5": 8, "5re": 5, "6": 0},
                   "30min": {"0": 16, "1": 25, "2": 18, "3": 12, "4": 10, "5": 12, "5re": 8, "6": 8},
                   "full": {"0": 20, "1": 40, "2": 25, "3": 18, "4": 12, "5": 20, "5re": 10, "6": 10}}


def budget(cfg, phase):
    b = cfg.get("budget_calls") or DEFAULT_BUDGETS.get(cfg.get("depth", "full"), DEFAULT_BUDGETS["full"])
    v = b.get(str(phase))
    if v is None: return "—"
    if str(phase) == "5" and str(cfg.get("audit_depth", "")).lower() == "high": v += 10
    return v


def build_shared(cfg, repo):
    lenses = ", ".join(l["id"] + " (" + l.get("audience", "") + ")" for l in cfg.get("lenses", []))
    batches = "\n".join(f"- {'★ ' if b.get('pilot') else ''}{b['name']}: {', '.join(b.get('modules', []))}" for b in cfg.get("batches", [])) or "- (Phase 0 proposes the batch plan)"
    seeds = "\n".join(f"- [PROTECTED] {s}" for s in cfg.get("seed_invariants", [])) or "- (none — Phase 2 proposes candidates)"
    return f"""# SHARED CONTEXT — {cfg['system']}
<!-- immutable for this run; identical bytes on every launch; place first in every helper prompt -->

## Principles
{PRINCIPLES}

## Tags
{TAGS}

## Taxonomy
{TAXONOMY}

## Output profile
{profile_line(cfg)}

## Lenses
{lenses}

## Batch plan
{batches}

## Seed invariants
{seeds}

## Repository map
{repo_map(repo)}

## Context rule
Do not read beyond your pack and its on-demand read list. If you need more, say what and why as a [GAP] — never guess, never roam. Extend the existing document files; never create per-batch copies.
"""


def section_titles(docs):
    """glossary terms established so far: IDX glossary table rows, if any."""
    p = os.path.join(docs, "01_IDX.md")
    if not os.path.exists(p): return "(no IDX yet)"
    rows = [l for l in open(p, encoding="utf-8").read().splitlines() if l.startswith("|") and not l.startswith("|---") and "Term" not in l]
    return "\n".join(rows[:60]) or "(no glossary rows yet)"


def next_ids(cfg, docs):
    def nxt(prefix, items):
        ns = [int(m.group(1)) for x in items if (m := re.match(prefix + r"-(\d+)", str(x.get("id", ""))))]
        return (max(ns) + 1) if ns else 1
    g, d = nxt("GAP", cfg.get("gaps", [])), nxt("DRIFT", cfg.get("drifts", []))
    br = 1; p = os.path.join(docs, "11_BRI.md")
    if os.path.exists(p):
        ns = [int(x) for x in re.findall(r"BR-(\d{3})", open(p, encoding="utf-8").read())]; br = (max(ns) + 1) if ns else 1
    return f"GAP-{g:03d}…GAP-{g+14:03d} · DRIFT-{d:03d}…DRIFT-{d+4:03d} · BR-{br:03d}…BR-{br+29:03d}"


def gaps_for(cfg, batch):
    g = [x for x in cfg.get("gaps", []) if batch and batch in str(x.get("found_in", ""))]
    d = [x for x in cfg.get("drifts", []) if batch and batch in json.dumps(x)]
    return "\n".join([f"- [{x['id']}] ({x.get('severity')}) {x.get('desc')} — Q: {x.get('question')}" for x in g] + [f"- [{x['id']}] {x.get('desc')} — A: {x.get('side_a')} | B: {x.get('side_b')}" for x in d]) or "(none touching this batch)"


def latest(logs, prefix):
    fs = sorted([f for f in os.listdir(logs) if re.match(rf"{prefix}-\d+\.json", f)], key=lambda f: int(re.search(r"-(\d+)\.json", f).group(1))) if os.path.isdir(logs) else []
    return json.load(open(os.path.join(logs, fs[-1]), encoding="utf-8")) if fs else None


def build_extractor(cfg, docs, batch, phase, stamp):
    b = next((x for x in cfg.get("batches", []) if x["name"] == batch), {"name": batch, "modules": []})
    owned = {"1": "02 ARC, 03 DAT, 04 MOD, 05 API, 06 INT, 07 XCC, 08 CNV, 09 UXF, 10 FLW (pass 1), 14 DEP — this batch's sections only; diagrams D1–D5, D7 per depth",
             "2": "11 BRI (this batch's rules), 12 TST; [PROTECTED] status lines", "3": "10 FLW (pass 2), 09 UXF closeout, 13 OPS, 01 IDX (draft); D6, D8 per depth",
             "4": "lenses/LENS-<ID>.md for this batch; D9, D10 at tracking depth"}.get(phase, "(see playbook-core §6)")
    return f"""# EXTRACTOR PACK — {batch} · Phase {phase}
Built from: {stamp} · {date.today().isoformat()} · call budget {budget(cfg, phase)} tool calls
Stopping at the cap with a clean handoff (documents saved, maturity lines updated, done/left/next in the tracker) is a correct outcome.
Before reporting, run `python3 scripts/doc_check.py docs --repo <repo> --batch "{batch}"` and resolve every unresolved citation and hedge; the checkpoint does not close otherwise.

## Modules in this batch (read on demand)
{chr(10).join('- ' + m for m in b.get('modules', [])) or '(none listed)'}

## Documents and sections this phase extends
{owned}

## Glossary established by earlier batches (use these names)
{section_titles(docs)}

## Open gaps / drift touching this batch
{gaps_for(cfg, batch)}

## Seed [PROTECTED] invariants
{chr(10).join('- ' + s for s in cfg.get('seed_invariants', [])) or '(none)'}

## Ids you may allocate
{next_ids(cfg, docs)}

## What to hand back
The extended documents with updated maturity lines; the doc_check summary; new GAP/DRIFT rows using the ids above; the Blocking/High questions as one-liners.
"""


def build_auditor(cfg, docs, batch, level, stamp):
    logs = os.path.join(docs, "_playbook", "logs"); chk = latest(logs, "check"); smp = latest(logs, "sample")
    if level == "none":
        return f"# AUDITOR PACK — {batch}\n\nAudit effort is NONE: no independent audit. doc_check ran: {('clean' if chk and not chk.get('blocking') else 'BLOCKING or missing')}. The tracker marks this run `audit: none`.\n"
    chk_line = (f"check {chk['check']} · {'BLOCKING' if chk['blocking'] else 'clean'} · citations {chk['citations']['resolved']}/{chk['citations']['total']} resolved ({chk['citations']['unresolved']} unresolved, {chk['citations']['external']} external) · untraced {chk['untraced_claims']} · hedges {chk['hedges']} · rule:TBD {chk['reconciliation']['rule_tbd']} · tree {chk['tree_hash']}" if chk else "(no doc_check report — run doc_check.py first; that is itself a finding)")
    sample = "\n\n".join(f"### {i+1}. {s['doc']} — `[src: {s['cite']}]`\n```\n{s.get('excerpt','')}\n```" for i, s in enumerate((smp or {}).get("sample", []))) or "(no sample — run doc_check.py --sample 15)"
    head = f"""# AUDITOR PACK — {batch or 'all batches'}  (audit effort: {level})
Built from: {stamp} · {date.today().isoformat()} · call budget {budget(cfg, '5')} tool calls
You did NOT write this corpus and must not trust its maturity lines — verify them. Your job is to find claims the documents make that the code does not support.
First: confirm the doc_check tree hash matches the current code (`doc_check.py` again if in doubt); a mismatch means the corpus describes different code.

## doc_check report
{chk_line}

## Citation sample — confirm each: does the cited member say what the document claims?
{sample}
Report hits / misses with the misses listed as: M-## | doc | citation | what the document claims | what the code says.
"""
    if level == "low": return head + "\n## Scope at LOW\nConfirm the sample only. No falsification attempts, no reads beyond the excerpts. Hit rate below 90% → recommend which batch/phase to re-run.\n"
    scope_docs = sorted(f for f in os.listdir(docs) if f.endswith(".md") and re.match(r"^\d\d_", f))
    mid = f"""
## Documents in scope
{chr(10).join('- ' + f for f in scope_docs)}
Lenses: {', '.join(l['id'] for l in cfg.get('lenses', []))}

## Consistency checks
- every FLW decision point resolves to a BR-###; every BR-### appears in TST; every [PROTECTED] has a Phase 2 status (MATCH / DRIFT / NOT-IN-THIS-BATCH)
- every GAP/DRIFT id in a document has a row in the log and vice versa
- every diagram node/edge carries [src:] or a gap/planned tag

## Falsification
Choose five claims yourself — [PROTECTED] rules and FLW steps first — and try to show the code contradicts them. Open files from the read list below only to check a named claim.

## Open gaps / drift
{gaps_for(cfg, batch) if batch else chr(10).join('- [' + g['id'] + '] ' + g.get('desc','') for g in cfg.get('gaps', [])[:30]) or '(none)'}
"""
    if level == "medium":
        return head + mid + "\n## On-demand read list\nThe batch's module folders and the shared folders Phase 0 named. Nothing else is in scope.\n"
    return head + mid + "\n## Scope at HIGH\nUnrestricted: the whole corpus and the whole repository. Look for the module the batch plan missed, the rule in a file no citation reaches, the convention nobody quoted. Report what you read in the audit's footer so the cost is visible.\n"


def build_scoped(cfg, docs, batch, misses_path, stamp):
    logs = os.path.join(docs, "_playbook", "logs")
    misses = json.load(open(misses_path, encoding="utf-8")) if misses_path and os.path.exists(misses_path) else {"misses": []}
    ms = misses.get("misses", [])
    smp = latest(logs, "sample")
    triggers = []
    if any(m.get("protected") is True or any("PROTECTED" in str(v).upper() for k, v in m.items() if k != "protected") for m in ms if isinstance(m, dict)): triggers.append("a miss was on a [PROTECTED] rule")
    changed = sh(["git", "diff", "--name-only", "HEAD", "--", "."], docs).split()
    scope_docs = [f for f in os.listdir(docs) if f.endswith(".md") and re.match(r"^\d\d_", f)]
    if scope_docs and len([c for c in changed if os.path.basename(c) in scope_docs]) > len(scope_docs) / 3: triggers.append("more than a third of the documents changed since the audit")
    attempt = misses.get("attempt", 1) + 1
    if attempt >= 3: triggers.append("attempt 3: misses persisted through a loop")
    block = f"""# SCOPED RE-AUDIT PACK — {batch or 'all batches'} (attempt {attempt})
Built from: {stamp} · {date.today().isoformat()} · call budget {budget(cfg, '5re')} tool calls
You did NOT write the corpus. A miss is RESOLVED only when the document now says what the cited member says, or the claim became [GAP]; a miss "resolved" by deleting the claim and its context without a [GAP] is a finding.

## Previous misses — re-check each
{chr(10).join(f"- {m.get('id','M-??')} | {m.get('doc','')} | `[src: {m.get('cite','')}]` | claimed: {m.get('claimed','')} | code: {m.get('code') or m.get('code_says','')}" for m in ms) or '(none listed)'}

## Fresh sample from changed sections (5)
{chr(10).join(f"- {s['doc']} — `[src: {s['cite']}]`" for s in (smp or {}).get('sample', [])[:5]) or '(run doc_check.py --sample 5 after the fix)'}

## Consistency checks — changed documents only
{chr(10).join('- ' + c for c in changed if c.endswith('.md')) or '(no document changes detected — was the fix applied?)'}
"""
    return block, triggers


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch"); ap.add_argument("--config", required=True); ap.add_argument("--repo", default=".")
    ap.add_argument("--phase", default="1"); ap.add_argument("--level", choices=["none", "low", "medium", "high"], default=None)
    ap.add_argument("--scoped", action="store_true"); ap.add_argument("--misses", default=None); ap.add_argument("--rotate-shared", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8")); pb = os.path.dirname(os.path.abspath(a.config)); docs = os.path.dirname(pb)
    packs = os.path.join(pb, "packs"); os.makedirs(packs, exist_ok=True)
    shared = build_shared(cfg, a.repo); h = hashlib.sha256(shared.encode()).hexdigest()[:12]
    sp, hp = os.path.join(packs, "shared.md"), os.path.join(packs, "shared.sha")
    if os.path.exists(hp) and open(hp).read().strip() != h and not a.rotate_shared:
        print(f"shared block kept (hash {open(hp).read().strip()}); new content differs ({h}) — pass --rotate-shared to replace (log it as a decision; it invalidates the cache)")
    else:
        open(sp, "w", encoding="utf-8").write(shared); open(hp, "w").write(h)
    stamp = sh(["git", "rev-parse", "--short", "HEAD"], a.repo).strip() or "no-git"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", a.batch).strip("-") or "all"
    level = a.level or cfg.get("audit_depth", "medium")
    print(f"shared   : {sp}  ~{tokens(open(sp, encoding='utf-8').read())} tok (hash {h}; cache prefix)")
    if a.scoped:
        block, triggers = build_scoped(cfg, docs, a.batch, a.misses, stamp)
        if triggers:
            r = build_auditor(cfg, docs, a.batch, "high" if level == "high" else "medium", stamp); p = os.path.join(packs, f"{slug}-auditor.md"); open(p, "w", encoding="utf-8").write(r)
            print("full_audit_required: true\n  - " + "\n  - ".join(triggers) + f"\nfull: {p}  ~{tokens(r)} tok (model/effort: resolved '5')")
        else:
            p = os.path.join(packs, f"{slug}-auditor-scoped.md"); open(p, "w", encoding="utf-8").write(block)
            print(f"full_audit_required: false\nscoped: {p}  ~{tokens(block)} tok (model/effort: resolved '5re')")
        return
    if a.phase == "5":
        r = build_auditor(cfg, docs, a.batch, level, stamp); p = os.path.join(packs, f"{slug}-auditor.md"); open(p, "w", encoding="utf-8").write(r)
        print(f"auditor  : {p}  ~{tokens(r)} tok (effort {level})")
    else:
        e = build_extractor(cfg, docs, a.batch, a.phase, stamp); p = os.path.join(packs, f"{slug}-extractor.md"); open(p, "w", encoding="utf-8").write(e)
        print(f"extractor: {p}  ~{tokens(e)} tok (phase {a.phase})")
    print(f"stamp    : {stamp} — collect step re-checks quoted files and marks [STALE] if they changed")


if __name__ == "__main__":
    main()
