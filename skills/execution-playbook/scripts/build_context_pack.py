#!/usr/bin/env python3
"""
build_context_pack.py — build the three context-pack files for one work-package launch:
  packs/shared.md            immutable for the run; byte-identical every launch; put FIRST in every helper prompt
  packs/WP-NN-builder.md     the builder's block (fence + on-demand read list + id ranges)
  packs/WP-NN-reviewer.md    the reviewer's block, sized by the run's reviewer effort (none|low|medium|high)
Rules and rationale: references/review-depth.md.

Usage:
    python3 build_context_pack.py WP-NN --config _playbook/run-config.json --scoped     # attempt 2+: scoped re-review block, or full if a blast-radius trigger fired
    python3 build_context_pack.py WP-NN --config _playbook/run-config.json [--playbook-dir _playbook] [--repo .]
        [--diff-base <git ref>] [--gate-log path] [--least-sure "text"] [--rotate-shared] [--level none|low|medium|high]

Reads:  run-config.json (principles are embedded here; decision rules, locked decisions, stack, tooling, effort, fidelity,
        reviewer effort, lenses), CLAUDE.md (conventions excerpt: the section headed "Conventions" if present, else first 60 lines),
        work-packages/WP-NN-*.md (whole file), adr/ADR-*.md referenced by id in the WP file (first 12 lines each),
        GAPS.md / DRIFTS or the config's gaps/drifts touching this WP, git (changed files + diff vs --diff-base; name-only if huge).
Writes: the three files, prints token estimates (chars/4) and warns above 25k for a block.
"""
import argparse, hashlib, json, os, re, subprocess, sys
from datetime import date

PRINCIPLES = """1. Frame before building — nothing passes a gate without a definition of done.
2. Tests before code — acceptance tests fail first; an untestable criterion is a [GAP], not a skipped test.
3. Build in one context, attack in another — the reviewer never shares the builder's reasoning.
4. Gates decide — commands + reviewer verdict; two fix loops then [BLOCKED]; never weaken a gate.
5. Gaps are truth — missing facts become [GAP] with a one-line question; never a plausible default.
6. Record why while you still know — ADRs at the gate, every decision in DECISIONS.md.
7. Decide at boundaries with the evidence in front of you — Decision Cards.
8. Pilot one work package before scaling."""

TAGS = """[src: File.ext#Member] / [src: SPEC §n]  backed here  ·  [GAP-###: q]  not known, nothing invented  ·  [DRIFT-###: A vs B]  sources disagree
[PLANNED]  deferred on purpose  ·  [UNTESTED: AC-##] / [tested: Class.Method]  ·  [ADR-###]  ·  [DC-###] / [DC-### AUTO rule n]  ·  [RISK-###]  ·  [STALE]  ·  [BLOCKED]"""

LENS_DEFAULT_CHECKS = {
    "CORRECTNESS": ["each AC has a test that asserts it and can fail", "edge cases the AC implies are covered or [PLANNED]", "error paths return the documented outcome", "spec mismatch is [DRIFT], not a silent fix", "no scope beyond the WP"],
    "SECURITY": ["every entry point authenticates and authorises server-side", "inputs validated at the boundary", "no secrets committed", "new dependencies known and pinned", "logs leak nothing sensitive"],
    "MAINTAINABILITY": ["follows CLAUDE.md and existing conventions", "no duplicated logic that already exists", "non-obvious choices have an ADR", "tests read as specification", "no hedging or TODO without a tag"],
    "OPERABILITY": ["configuration externalised and documented", "failures logged with context", "timeouts/retries/idempotency where calls leave the process", "migrations reversible or [RISK]-logged", "gate commands reproducible from a clean checkout"],
}


def sh(cmd, cwd, default=""):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return default


def tokens(s): return len(s) // 4


def conventions_excerpt(pb):
    p = os.path.join(pb, "CLAUDE.md")
    if not os.path.exists(p): return "(no CLAUDE.md yet — Phase 0 writes it)"
    t = open(p, encoding="utf-8").read()
    m = re.search(r"(^#+\s*Conventions.*?)(?=^#\s|\Z)", t, re.S | re.M)
    return (m.group(1) if m else "\n".join(t.splitlines()[:60])).strip()


def repo_map(repo):
    out = []
    try:
        for name in sorted(os.listdir(repo)):
            if name.startswith(".") or name in ("node_modules", "bin", "obj", "dist", "_playbook"): continue
            p = os.path.join(repo, name)
            if os.path.isdir(p):
                n = sum(len(f) for _, _, f in os.walk(p))
                out.append(f"- {name}/  ({n} files)")
            else:
                out.append(f"- {name}")
    except Exception:
        out.append("(repo not readable)")
    return "\n".join(out[:60])


def build_shared(cfg, pb, repo):
    rules = "\n".join(f"{i}. {r}" for i, r in enumerate(cfg.get("decision_rules", []), 1))
    locked = "\n".join(f"- {x}" for x in cfg.get("locked_decisions", [])) or "- (none beyond the stack)"
    return f"""# SHARED CONTEXT — {cfg['task']}
<!-- immutable for this run; identical bytes on every launch; place first in every helper prompt -->

## Principles
{PRINCIPLES}

## Tags
{TAGS}

## Decision rules (unattended)
{rules}

## Locked decisions
{locked}

## Stack
{', '.join(cfg.get('stack', [])) or '(not a coding task / not fixed)'}

## Fidelity & effort
Fidelity: {cfg.get('fidelity', 'mvp')} · effort logic {cfg.get('effort', {}).get('logic', 'recommended')} / architecture {cfg.get('effort', {}).get('architecture', 'recommended')} / ui {cfg.get('effort', {}).get('ui', 'recommended')}

## Conventions (from CLAUDE.md)
{conventions_excerpt(pb)}

## Repository map
{repo_map(repo)}

## Context rule
Do not read beyond your pack and its on-demand read list. If you need more, say what and why as a [GAP] — never guess, never roam.
"""


def wp_file(pb, wp):
    d = os.path.join(pb, "work-packages")
    if not os.path.isdir(d): return None, ""
    for f in sorted(os.listdir(d)):
        if f.startswith(wp): return f, open(os.path.join(d, f), encoding="utf-8").read()
    return None, ""


def section(md, title):
    m = re.search(rf"^##\s*{re.escape(title)}.*?$(.*?)(?=^##\s|\Z)", md, re.S | re.M | re.I)
    return m.group(1).strip() if m else ""


def adr_summaries(pb, ids):
    out = []
    d = os.path.join(pb, "adr")
    for i in sorted(set(ids)):
        p = next((os.path.join(d, f) for f in (os.listdir(d) if os.path.isdir(d) else []) if f.startswith(i)), None)
        if p:
            lines = open(p, encoding="utf-8").read().splitlines()[:12]
            out.append("\n".join(lines))
        else:
            out.append(f"# {i} — (file not found) [GAP: ADR referenced but missing]")
    return "\n\n".join(out) or "(none referenced)"


def gaps_for(cfg, wp):
    g = [x for x in cfg.get("gaps", []) if wp in str(x.get("found_in", "")) or wp in str(x.get("blocks", ""))]
    d = [x for x in cfg.get("drifts", []) if wp in json.dumps(x)]
    lines = [f"- [{x['id']}] ({x.get('severity')}) {x.get('desc')} — Q: {x.get('question')}" + (f" — answered: {x['answered']}" if x.get("answered") else "") for x in g]
    lines += [f"- [{x['id']}] {x.get('desc')} — A: {x.get('side_a')} | B: {x.get('side_b')}" for x in d]
    return "\n".join(lines) or "(none touching this WP)"


def next_ids(cfg):
    def nxt(prefix, items, key="id"):
        ns = [int(m.group(1)) for x in items if (m := re.match(prefix + r"-(\d+)", str(x.get(key, ""))))]
        return (max(ns) + 1) if ns else 1
    g, d, a = nxt("GAP", cfg.get("gaps", [])), nxt("DRIFT", cfg.get("drifts", [])), nxt("ADR", cfg.get("adrs", []))
    return f"GAP-{g:03d}…GAP-{g+9:03d} · DRIFT-{d:03d}…DRIFT-{d+4:03d} · ADR-{a:03d}…ADR-{a+2:03d}"


def changed(repo, base):
    names = sh(["git", "diff", "--name-only", base], repo) if base else sh(["git", "status", "--porcelain"], repo)
    if not base: names = "\n".join(l[3:] for l in names.splitlines())
    diff = sh(["git", "diff", base] if base else ["git", "diff"], repo)
    if len(diff) > 60000: diff = diff[:60000] + "\n… (diff truncated at 60k chars; open files from the read list for the rest)"
    return names.strip(), diff


def build_builder(cfg, pb, wp, wpname, wpmd, stamp):
    tools = cfg.get("tooling", "claude-only")
    tool_lines = "Claude only" if tools == "claude-only" else "\n".join(f"- {t['tool']}: {t.get('used_for','')} → {t.get('produces','')} ({t.get('availability','')})" for t in tools if wp in t.get("wps", []) or "all" in t.get("wps", [])) or "Claude only for this WP"
    adrs = re.findall(r"ADR-\d{3}", wpmd)
    fence = section(wpmd, "Outputs") or "(declare in Design: files this WP may change)"
    reads = section(wpmd, "Inputs") or "(declare in Design: files this WP may read on demand)"
    return f"""# BUILDER PACK — {wp} {wpname}
Built from: {stamp} · {date.today().isoformat()} · fidelity {cfg.get('fidelity','mvp')} · reviewer effort {cfg.get('review_depth','medium')}
Call budget for this stage: {cfg.get('budget_calls', {}).get('build', '—')} tool calls. Stopping at the cap with a clean handoff (compiles, nothing committed, done/left/next in the WP file) is a correct outcome. Gate: run `scripts/gate.py` ONCE and read `--show`. Sweep: `scripts/mutate.py` with a mutant list incl. sentinels; read the table.

## Work package (verbatim)
{wpmd.strip()}

## Contracts & inputs it touches (quoted with [src:] — read on demand)
{reads}

## Files it may change (the fence)
{fence}
Needing a file outside the fence → [GAP] + Decision Card. Do not edit it; do not stop silently.

## Decisions it depends on
{adr_summaries(pb, adrs)}

## Open gaps / drift touching this WP
{gaps_for(cfg, wp)}

## Tools for this WP's outputs
{tool_lines}

## Ids you may allocate
{next_ids(cfg)}

## What to hand back
Build note (what changed, least-sure areas, rules applied as [DC-### AUTO rule n]); every AC → [tested:] or [UNTESTED:]; new GAP/DRIFT/ADR entries using the ids above; nothing else.
"""


def build_reviewer(cfg, pb, wp, wpname, wpmd, level, names, diff, gate_log, least_sure, stamp):
    if level == "none":
        return f"# REVIEWER PACK — {wp}\n\nReviewer effort is NONE for this run: no independent review. Gate = commands + builder self-check. Gate record must say `review: none`.\n"
    acs = section(wpmd, "Acceptance criteria") or "(no AC section found — that is itself a Blocking finding)"
    lens_ids = [l["id"] for l in cfg.get("lenses", [])]
    if cfg.get("fidelity") == "poc": lens_ids = ["CORRECTNESS"]
    checks = []
    for l in cfg.get("lenses", []):
        if l["id"] in lens_ids:
            cs = l.get("checks") or LENS_DEFAULT_CHECKS.get(l["id"], [])
            checks.append(f"### {l['id']} — {l.get('perspective','')}\n" + "\n".join(f"- {c}" for c in cs))
    checks = "\n\n".join(checks)
    head = f"""# REVIEWER PACK — {wp} {wpname}  (reviewer effort: {level})
Built from: {stamp} · {date.today().isoformat()} · call budget {cfg.get('budget_calls', {}).get('review', '—')}
You have NOT seen the builder's reasoning and must not trust the build note's claims — verify them.
Your job is to FAIL this work package if you can. Verdict: PASS only with zero Blocking and zero High findings.
Findings as: F-## | lens | Blocking/High/Low | what is wrong | evidence [src:] | AC affected. Write review/{wp}-review.md.

## Acceptance criteria
{acs}

## Gate output
{gate_log or '(no gate summary in logs/ — the orchestrator runs gate.py once before the review; do not run it yourself unless a trigger applies)'}

## Changed files
{names or '(none reported)'}

## Diff
```diff
{diff or '(empty)'}
```

## Lens checks in force
{checks}

## Fail-first evidence (from the WP file)
{section(wpmd, "Fail-first evidence") or '(missing — that is a High finding: tests-before-code was not evidenced)'}

## Mutation table (from the WP file)
{section(wpmd, "Mutation table") or ('(none — self-check is Minimal for this run)' if cfg.get('self_check', 'standard') == 'minimal' else '(missing — High finding: the sweep was not done or not recorded)')}
Re-apply three mutants from this table (the two you judge most likely wrong and one at random); confirm the named test fails; restore. A mutant that does not reproduce → High against the table. An obvious mutation point not listed → High against the sweep.
"""
    if level == "low":
        return head + """
## Scope at LOW
Confirm each AC has a test that asserts it and can fail (open the test). Read the diff against the AC wording. Answer only the lens checks the diff alone can answer; for the rest write "not checkable at this effort". No reads outside the diff.
"""
    adrs = re.findall(r"ADR-\d{3}", wpmd)
    mid = f"""
## Contracts this WP touches (quoted, [src:])
{section(wpmd, "Inputs") or '(none quoted — if the WP touches a contract, that is a High finding against Design)'}

## Decisions it depends on
{adr_summaries(pb, adrs)}

## Builder's least-sure items (hints, not claims)
{least_sure or '(none given)'}

## Open gaps / drift touching this WP
{gaps_for(cfg, wp)}

## Falsification
Attempt to falsify at least five claims: the ACs first, then the least-sure items. Confirm no gate command, test or threshold was weakened since Design (diff them). Hedging words in WP docs without a tag → Low finding each.
"""
    if level == "medium":
        return head + mid + f"""
## On-demand read list
{section(wpmd, "Inputs") or '(as declared in Design)'}
Open a file from this list only to check a specific claim; name the claim in the finding. Nothing else is in scope.
"""
    return head + mid + """
## Scope at HIGH
Unrestricted: PLAYBOOK.md, CLAUDE.md, every ADR, earlier WP files and reviews, the whole repository. Look for the convention nobody quoted, the earlier finding that recurs, the contract three modules away. Report what you read in the review's footer so the cost is visible.
"""


# ---------------------------------------------------------------- scoped re-review
def parse_patch_files(patch):
    """{path: hunk text} from a unified diff."""
    out = {}; cur = None; buf = []
    for line in patch.splitlines():
        if line.startswith("diff --git"):
            if cur: out[cur] = "\n".join(buf)
            cur = line.split(" b/")[-1].strip(); buf = []
        elif cur is not None: buf.append(line)
    if cur: out[cur] = "\n".join(buf)
    return out


def latest_review(pb, wp):
    d = os.path.join(pb, "review")
    if not os.path.isdir(d): return None, ""
    fs = sorted(f for f in os.listdir(d) if f.startswith(wp) and f.endswith(".md"))
    if not fs: return None, ""
    return fs[-1], open(os.path.join(d, fs[-1]), encoding="utf-8").read()


def findings_from(review_md):
    return [l for l in review_md.splitlines() if re.match(r"\s*\|?\s*F-\d+", l)]


ASSERT_RX = re.compile(r"\b(assert|expect|should|Assert\.|\.toBe|\.toEqual|Should\(|Verify\()")
NOISE = ("_playbook/", "__pycache__", ".pytest_cache", "node_modules", "bin/", "obj/", "dist/", ".venv", "venv/")


def net_assert_removed(hunk):
    """(- assertion lines) - (+ assertion lines) in a diff hunk; grows when a fix weakens tests."""
    rem = sum(1 for l in hunk.splitlines() if l.startswith("-") and not l.startswith("---") and ASSERT_RX.search(l))
    add = sum(1 for l in hunk.splitlines() if l.startswith("+") and not l.startswith("+++") and ASSERT_RX.search(l))
    return rem - add


def test_weakened(prev_hunk, cur_hunk):
    return net_assert_removed(cur_hunk or "") > net_assert_removed(prev_hunk or "")


def scoped_block(cfg, pb, wp, wpname, wpmd, repo, stamp):
    logs = os.path.join(pb, "logs")
    gates = sorted([f for f in os.listdir(logs) if re.match(rf"{wp}-gate-\d+\.json", f)], key=lambda f: int(re.search(r"-(\d+)\.json", f).group(1))) if os.path.isdir(logs) else []
    if len(gates) < 1:
        return None, ["no previous gate summary — nothing to scope against"], ""
    prev_n = int(re.search(r"-(\d+)\.json", gates[-1]).group(1))
    prev_patch_p = os.path.join(logs, f"{wp}-gate-{prev_n}.patch")
    prev_patch = open(prev_patch_p, encoding="utf-8").read() if os.path.exists(prev_patch_p) else ""
    _, cur_patch = (0, sh(["git", "diff", "HEAD"], repo))
    prev_f, cur_f = parse_patch_files(prev_patch), parse_patch_files(cur_patch)
    pbrel = os.path.relpath(os.path.abspath(pb), os.path.abspath(repo)).rstrip("/") + "/"
    noise = list(NOISE) + ([pbrel] if not pbrel.startswith("..") else [])
    prev_f = {f: h for f, h in prev_f.items() if not any(n in f for n in noise)}
    cur_f = {f: h for f, h in cur_f.items() if not any(n in f for n in noise)}
    changed = sorted(f for f in set(prev_f) | set(cur_f) if prev_f.get(f) != cur_f.get(f))
    fence = [l.strip("- ").strip() for l in section(wpmd, "Outputs").splitlines() if l.strip()]
    contracts = re.findall(r"\[src:\s*([^#\]\s]+)", section(wpmd, "Inputs"))
    wp_files = set(f for f in fence if "/" in f or "." in f) | set(cur_f)
    triggers = []
    outside = [f for f in changed if fence and not any(f.endswith(x.split("(")[0].strip()) or x.split("(")[0].strip().endswith(f) for x in fence)]
    if fence and outside: triggers.append(f"diff touches files outside the WP fence: {', '.join(outside[:5])}")
    hit_c = [c for c in contracts if any(f.endswith(c) or c.endswith(f) for f in changed)]
    if hit_c: triggers.append(f"diff touches a quoted contract: {', '.join(hit_c)}")
    tests = [f for f in changed if re.search(r"(test|spec)", f, re.I)]
    weakened = [f for f in tests if test_weakened(prev_f.get(f), cur_f.get(f)) or (f in prev_f and f not in cur_f and net_assert_removed(prev_f[f]) < 0)]
    if weakened: triggers.append(f"test file reduced or removed: {', '.join(weakened)}")
    if wp_files and len(changed) > len(wp_files) / 3 and len(changed) > 2: triggers.append(f"{len(changed)} of ~{len(wp_files)} WP files changed (> 1/3)")
    rev_name, rev_md = latest_review(pb, wp); findings = findings_from(rev_md)
    if any(re.search(r"(Blocking|High)", f) and re.search(r"(SECURITY|COMPLIANCE|DOMAIN)", f) for f in findings): triggers.append("a prior finding was Blocking/High on SECURITY, COMPLIANCE or DOMAIN")
    if "[PROTECTED]" in wpmd: triggers.append("WP touches a [PROTECTED] rule")
    attempt = prev_n + 1
    if attempt >= 3: triggers.append("attempt 3: findings persisted through a loop")
    hunks = "\n\n".join(f"### {f}\n```diff\n{(cur_f.get(f) or '(file reverted / no longer in diff)')[:4000]}\n```" for f in changed) or "(no changes since the previous gate — nothing to re-review; was the fix applied?)"
    mut = section(wpmd, "Mutation table")
    block = f"""# SCOPED REVIEWER PACK — {wp} {wpname}  (attempt {attempt}; scoped re-review)
Built from: {stamp} · {date.today().isoformat()} · call budget {cfg.get('budget_calls', {}).get('rereview', '—')}
You have NOT seen the builder's reasoning. Confirm, do not assume: a prior finding is RESOLVED only when its mutant is killed
by a test that asserts the behaviour; RESOLVED BY WEAKENING is Blocking.
First action: `python3 scripts/gate.py {wp} --playbook-dir _playbook --verify`.

## Acceptance criteria
{section(wpmd, "Acceptance criteria") or '(no AC section — Blocking)'}

## Attempt {prev_n} findings ({rev_name or 'no review file found — Blocking'})
{chr(10).join(findings) or '(none parsed — open ' + str(rev_name) + ')'}

## Diff since gate attempt {prev_n} ({len(changed)} file(s))
{hunks}

## Test files touched since attempt {prev_n}
{chr(10).join('- ' + f + ('  ⚠ assertions reduced' if f in weakened else '') for f in tests) or '(none)'}

## Mutation table (re-apply every row added since attempt {prev_n}, plus each prior finding's mutant)
{mut or '(missing — High: the sweep was not recorded)'}

## Lens checks — apply to the diff only
{chr(10).join('### ' + l['id'] + chr(10) + chr(10).join('- ' + c for c in (l.get('checks') or LENS_DEFAULT_CHECKS.get(l['id'], []))) for l in cfg.get('lenses', []))}

## Stop and report "full review required" if you find
a change outside the fence, a changed quoted contract, a reduced test, or more than a third of the WP's files changed.
"""
    return block, triggers, str(attempt)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wp"); ap.add_argument("--config", required=True); ap.add_argument("--playbook-dir", default=None); ap.add_argument("--repo", default=".")
    ap.add_argument("--diff-base", default=None); ap.add_argument("--gate-log", default=None, help="(legacy) raw log; prefer the gate.py summary, auto-detected in logs/"); ap.add_argument("--least-sure", default="")
    ap.add_argument("--rotate-shared", action="store_true"); ap.add_argument("--scoped", action="store_true", help="attempt 2+: scoped re-review block from prior findings + diff since previous gate; prints full_review_required"); ap.add_argument("--level", choices=["none", "low", "medium", "high"], default=None)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    pb = a.playbook_dir or os.path.dirname(os.path.abspath(a.config))
    level = a.level or cfg.get("review_depth", "medium")
    packs = os.path.join(pb, "packs"); os.makedirs(packs, exist_ok=True)

    shared = build_shared(cfg, pb, a.repo); h = hashlib.sha256(shared.encode()).hexdigest()[:12]
    sp = os.path.join(packs, "shared.md"); hp = os.path.join(packs, "shared.sha")
    if os.path.exists(hp) and open(hp).read().strip() != h and not a.rotate_shared:
        print(f"shared block unchanged on disk (hash {open(hp).read().strip()}); new content differs ({h}) — keeping the cached version. Pass --rotate-shared to replace it (log it as a decision: it invalidates the cache).")
    else:
        open(sp, "w", encoding="utf-8").write(shared); open(hp, "w").write(h)
    shared_tok = tokens(open(sp, encoding="utf-8").read())

    wpname, wpmd = wp_file(pb, a.wp)
    if not wpmd:
        sys.exit(f"no work-packages/{a.wp}-*.md found — run Design first")
    stamp = (sh(["git", "rev-parse", "--short", "HEAD"], a.repo).strip() or "no-git")
    names, diff = changed(a.repo, a.diff_base)
    gate_log = ""
    logs = os.path.join(pb, "logs")
    gsums = sorted([f for f in os.listdir(logs) if re.match(rf"{a.wp}-gate-\d+\.json", f)], key=lambda f: int(re.search(r"-(\d+)\.json", f).group(1))) if os.path.isdir(logs) else []
    if gsums:
        g = json.load(open(os.path.join(logs, gsums[-1]), encoding="utf-8"))
        gate_log = f"attempt {g['attempt']} · overall {g['overall']} · tree {g['tree_hash']} · {g['duration_s']}s · log {g.get('log','')}\n" + "\n".join(
            f"- `{c['cmd'][:80]}` → exit {c['exit']} · tests {c['tests'] or '—'}" + (f"\n  first failure @offset {c['log_offset']}:\n```\n{c['first_failure']}\n```" if c.get('first_failure') else "") for c in g["commands"])
        gate_log += "\nFIRST ACTION: `python3 scripts/gate.py " + a.wp + " --playbook-dir _playbook --verify` — a tree-hash MISMATCH is a Blocking finding. Open the log only at a failing offset."
    elif a.gate_log and os.path.exists(a.gate_log):
        gate_log = "(raw log tail — prefer gate.py summaries)\n" + open(a.gate_log, encoding="utf-8").read()[-4000:]

    if a.scoped:
        block, triggers, attempt = scoped_block(cfg, pb, a.wp, wpname, wpmd, a.repo, stamp)
        full = bool(triggers)
        if block and not full:
            rp = os.path.join(packs, f"{a.wp}-reviewer-scoped-{attempt}.md"); open(rp, "w", encoding="utf-8").write(block)
            print(f"full_review_required: false\nscoped: {rp}  ~{tokens(block)} tok  (model/effort: resolved '3re')")
        else:
            r = build_reviewer(cfg, pb, a.wp, wpname, wpmd, level, names, diff, gate_log, a.least_sure, stamp)
            rp = os.path.join(packs, f"{a.wp}-reviewer.md"); open(rp, "w", encoding="utf-8").write(r)
            print("full_review_required: true\n  - " + "\n  - ".join(triggers) + f"\nfull: {rp}  ~{tokens(r)} tok  (model/effort: resolved '3')")
        return
    b = build_builder(cfg, pb, a.wp, wpname, wpmd, stamp); bp = os.path.join(packs, f"{a.wp}-builder.md"); open(bp, "w", encoding="utf-8").write(b)
    r = build_reviewer(cfg, pb, a.wp, wpname, wpmd, level, names, diff, gate_log, a.least_sure, stamp); rp = os.path.join(packs, f"{a.wp}-reviewer.md"); open(rp, "w", encoding="utf-8").write(r)

    print(f"shared  : {sp}  ~{shared_tok} tok  (hash {h}; cache prefix)")
    print(f"builder : {bp}  ~{tokens(b)} tok{'  WARNING >25k — grow the read list, shrink the quotes' if tokens(b) > 25000 else ''}")
    print(f"reviewer: {rp}  ~{tokens(r)} tok  (effort {level}){'  WARNING >25k' if tokens(r) > 25000 else ''}")
    print(f"stamp   : {stamp} — collect step must re-check quoted files against the tree and mark [STALE] if they changed")


if __name__ == "__main__":
    main()
