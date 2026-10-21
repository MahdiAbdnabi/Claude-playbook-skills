#!/usr/bin/env python3
"""
mutate.py — the mutation-sweep harness. Applies each mutant in a private git worktree (fallback: temp copy),
runs the tests, restores by construction, and writes one summary table the helper reads instead of doing
edit/run/restore by hand. Includes SENTINELS so a broken harness cannot report "all killed" unnoticed.
Rules: references/self-check.md §2 and references/step-budgets.md §1.

Usage:
    python3 mutate.py WP-NN --mutants mutants.json --playbook-dir _playbook [--repo .] [--full-cmd "npm test"] [--timeout 600]

mutants.json:
{
  "test_cmd": "npm test -- --silent",                 # default command; per-mutant "tests" overrides it (a narrower run)
  "mutants": [
    {"id": "M1", "file": "src/risk.ts", "find": "worst >= current", "replace": "worst > current",
     "point": "RiskEngine#combine tie rule [src: src/risk.ts#combine]", "tests": "npm test -- risk.spec",
     "expect": "killed"},                                                 # optional sentinel: killed | survived
    {"id": "M2", "file": "src/storage.ts", "find": "if (window.localStorage)", "replace": "if (true)",
     "point": "env guard [src: src/storage.ts#safeGet]", "guard": "environment"}   # guard=environment → never a removal candidate
  ]
}
"find" must occur exactly once in "file" (the harness refuses ambiguous mutants).

Behaviour per mutant: worktree at HEAD + current working-tree diff → apply → run "tests" (or test_cmd) → if it PASSES and
--full-cmd is given, run the full suite before calling it a survivor → record → remove worktree. Nothing in the real tree
is ever edited.  Sentinels: every run should include at least one expect:"killed" and one expect:"survived" entry; a
sentinel whose result differs from its expectation FAILS THE HARNESS (exit 3) — the table is not to be trusted.
Writes: logs/WP-NN-mutation.json and logs/WP-NN-mutation.md (the table to paste into the WP file).
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time


def sh(cmd, cwd, shell=False, timeout=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 124, "[timeout]"


def make_private_copy(repo):
    """git worktree at HEAD with the working-tree diff applied; falls back to a temp copy."""
    rc, _ = sh(["git", "rev-parse", "HEAD"], repo)
    tmp = tempfile.mkdtemp(prefix="mutant-")
    if rc == 0:
        wt = os.path.join(tmp, "wt")
        rc2, out = sh(["git", "worktree", "add", "--detach", wt, "HEAD"], repo)
        if rc2 == 0:
            _, diff = sh(["git", "diff", "HEAD", "--binary"], repo)
            if diff.strip():
                p = os.path.join(tmp, "wip.patch"); open(p, "w", encoding="utf-8").write(diff)
                sh(["git", "apply", "--allow-empty", p], wt)
            _, untracked = sh(["git", "ls-files", "--others", "--exclude-standard"], repo)
            for f in untracked.split():
                src, dst = os.path.join(repo, f), os.path.join(wt, f)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.isfile(src): shutil.copy2(src, dst)
            # link heavy dependency dirs instead of copying them
            for dep in ("node_modules", ".venv", "venv", "packages"):
                s, d = os.path.join(repo, dep), os.path.join(wt, dep)
                if os.path.isdir(s) and not os.path.exists(d):
                    try: os.symlink(s, d)
                    except OSError: pass
            return wt, ("worktree", tmp)
    wt = os.path.join(tmp, "copy")
    shutil.copytree(repo, wt, ignore=shutil.ignore_patterns(".git", "node_modules", ".venv", "venv", "bin", "obj", "dist"), symlinks=True)
    for dep in ("node_modules", ".venv", "venv"):
        s, d = os.path.join(repo, dep), os.path.join(wt, dep)
        if os.path.isdir(s) and not os.path.exists(d):
            try: os.symlink(s, d)
            except OSError: pass
    return wt, ("copy", tmp)


def destroy(repo, kind, tmp):
    if kind == "worktree":
        sh(["git", "worktree", "remove", "--force", os.path.join(tmp, "wt")], repo); sh(["git", "worktree", "prune"], repo)
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wp"); ap.add_argument("--mutants", required=True); ap.add_argument("--playbook-dir", required=True)
    ap.add_argument("--repo", default="."); ap.add_argument("--full-cmd", default=None); ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    spec = json.load(open(a.mutants, encoding="utf-8")); repo = os.path.abspath(a.repo)
    logs = os.path.join(a.playbook_dir, "logs"); os.makedirs(logs, exist_ok=True)
    default_cmd = spec.get("test_cmd"); rows = []; t0 = time.time(); harness_ok = True
    sentinels = {"killed": 0, "survived": 0}

    # Baseline guard: the UNMUTATED tree must pass in a private copy, or every "killed" below is indistinguishable
    # from a broken environment (missing module, wrong cwd, failing import).
    base_cmds = sorted({m.get("tests") or default_cmd for m in spec.get("mutants", []) if (m.get("tests") or default_cmd)} | ({a.full_cmd} if a.full_cmd else set()))
    wt, (kind, tmp) = make_private_copy(repo)
    try:
        for cmd in base_cmds:
            rc, out = sh(cmd, wt, shell=True, timeout=a.timeout)
            if rc != 0:
                tail = "\n".join(out.splitlines()[-12:])
                print(f"HARNESS FAILED — baseline (unmutated) run fails in the private copy for `{cmd}`:\n{tail}\nFix the environment or the command; no mutant was evaluated.")
                json.dump({"wp": a.wp, "harness_ok": False, "baseline_failed": cmd, "tail": tail, "rows": []}, open(os.path.join(logs, f"{a.wp}-mutation.json"), "w", encoding="utf-8"), indent=2)
                sys.exit(3)
    finally:
        destroy(repo, kind, tmp)

    for m in spec.get("mutants", []):
        row = {"id": m["id"], "point": m.get("point", ""), "file": m["file"], "mutant": f'{m["find"]!r} → {m["replace"]!r}', "guard": m.get("guard", ""), "expect": m.get("expect")}
        fp = os.path.join(repo, m["file"])
        try: src = open(fp, encoding="utf-8").read()
        except OSError: row.update(result="ERROR", note="file not found"); rows.append(row); harness_ok = False; continue
        if src.count(m["find"]) != 1:
            row.update(result="ERROR", note=f'"find" occurs {src.count(m["find"])} times — must be exactly 1'); rows.append(row); harness_ok = False; continue
        wt, (kind, tmp) = make_private_copy(repo)
        try:
            wfp = os.path.join(wt, m["file"]); wsrc = open(wfp, encoding="utf-8").read()
            if wsrc.count(m["find"]) != 1: row.update(result="ERROR", note="private copy differs from tree"); harness_ok = False; rows.append(row); continue
            open(wfp, "w", encoding="utf-8").write(wsrc.replace(m["find"], m["replace"], 1))
            cmd = m.get("tests") or default_cmd
            if not cmd: row.update(result="ERROR", note="no test command"); harness_ok = False; rows.append(row); continue
            t1 = time.time(); rc, out = sh(cmd, wt, shell=True, timeout=a.timeout)
            row["test_cmd"] = cmd; row["duration_s"] = round(time.time() - t1, 1)
            if rc != 0:
                row["result"] = "killed"; row["failing_output"] = "\n".join(out.splitlines()[-15:])
            else:
                if a.full_cmd and cmd != a.full_cmd:
                    rc2, out2 = sh(a.full_cmd, wt, shell=True, timeout=a.timeout)
                    if rc2 != 0:
                        row["result"] = "killed"; row["note"] = "killed by full suite, not by the narrow run — widen 'tests'"; row["failing_output"] = "\n".join(out2.splitlines()[-15:])
                    else: row["result"] = "survived"
                else: row["result"] = "survived"
            if row["result"] == "survived" and row["guard"] == "environment":
                row["resolution_rule"] = "environment guard: write a test with the environment faked; removal is not an option"
        finally:
            destroy(repo, kind, tmp)
        if row.get("expect"):
            sentinels[row["expect"]] += 1
            if row["expect"] != row.get("result"):
                row["note"] = f"SENTINEL MISMATCH: expected {row['expect']}, got {row.get('result')}"; harness_ok = False
        rows.append(row)

    # restore check on the REAL tree: nothing should have changed
    _, dirty_before = sh(["git", "status", "--porcelain"], repo)
    summ = {"wp": a.wp, "duration_s": round(time.time() - t0, 1), "harness_ok": harness_ok,
            "sentinels": sentinels, "listed": len(rows), "killed": sum(1 for r in rows if r.get("result") == "killed"),
            "survived": sum(1 for r in rows if r.get("result") == "survived"), "errors": sum(1 for r in rows if r.get("result") == "ERROR"), "rows": rows}
    jp = os.path.join(logs, f"{a.wp}-mutation.json"); json.dump(summ, open(jp, "w", encoding="utf-8"), indent=2)
    md = [f"## Mutation table — {a.wp} (harness {'OK' if harness_ok else 'FAILED'}; sentinels killed {sentinels['killed']}, survived {sentinels['survived']})",
          "| # | Mutation point [src:] | Mutant | Result | Test / note | Resolution |", "|---|---|---|---|---|---|"]
    for r in rows:
        res = r.get("result", "?"); note = r.get("note", "") or (r.get("test_cmd", "") if res == "killed" else "")
        resolution = "killed" if res == "killed" else (r.get("resolution_rule") or ("write the test that kills it (or a written static argument — never for env guards)" if res == "survived" else "fix the mutant spec"))
        md.append(f"| {r['id']} | {r.get('point','')} | `{r['mutant']}` | **{res}** | {note} | {resolution} |")
    mp = os.path.join(logs, f"{a.wp}-mutation.md"); open(mp, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"{'HARNESS OK' if harness_ok else 'HARNESS FAILED — do not trust this table'} · listed {summ['listed']} · killed {summ['killed']} · survived {summ['survived']} · errors {summ['errors']} · {summ['duration_s']}s")
    if not (sentinels["killed"] and sentinels["survived"]):
        print("WARNING: include at least one expect:'killed' and one expect:'survived' sentinel so a broken harness is detected.")
    print(f"table: {mp}  (paste the table into the WP file)  summary: {jp}")
    sys.exit(0 if harness_ok else 3)


if __name__ == "__main__":
    main()
