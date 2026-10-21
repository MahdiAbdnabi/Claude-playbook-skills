#!/usr/bin/env python3
"""
gate.py — run a work package's gate commands ONCE, write the full log to a file and a structured
summary the helpers read instead of the log, and stamp both with the tree hash they ran on.
Rules: references/step-budgets.md §2 and §4.

Usage:
    python3 gate.py WP-NN --playbook-dir _playbook [--repo .] [--cmd "..." ...] [--attempt N] [--timeout 1800]
        commands default to the "## Gate commands" section of work-packages/WP-NN-*.md (one per line, '#' comments ignored)
    python3 gate.py WP-NN --playbook-dir _playbook --verify            # check the current tree against the latest summary's hash
    python3 gate.py WP-NN --playbook-dir _playbook --show [--attempt N] # print the summary (what a helper should read)

Writes: logs/WP-NN-gate-<attempt>.log (full output)  .json (summary)  .patch (git diff HEAD at run time, for scoped re-reviews)
Summary: {wp, attempt, started, duration_s, tree_hash, commit, overall: PASS|FAIL,
          commands: [{cmd, exit, duration_s, tests: {passed, failed, skipped} | null, first_failure: "<=25 lines", log_offset}]}
Tree hash = commit + sha256(git diff HEAD) + sha256(untracked file list+sizes). The reviewer compares it with the current tree
BEFORE reading anything else; a mismatch means the log describes different code.
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from datetime import datetime

COUNT_PATTERNS = [  # (regex, passed, failed, skipped) — common runners
    (r"Passed!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+)", 2, 1, 3),   # dotnet test
    (r"Failed!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+)", 2, 1, 3),
    (r"Tests:\s*(?:(\d+) failed,\s*)?(?:(\d+) skipped,\s*)?(\d+) passed", 3, 1, 2),       # jest
    (r"(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) skipped)?", 1, 2, 3),                # pytest / vitest / playwright
    (r"(\d+) passing(?:\s*\(.*?\))?\s*(?:(\d+) failing)?", 1, 2, None),                   # mocha
    (r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", None, 2, 4),  # junit/maven (run count only)
]


def sh(cmd, cwd, shell=False):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=shell)
    return r.returncode, r.stdout + r.stderr


NOISE = ("_playbook/", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", "bin/", "obj/", "dist/", ".venv", "venv/", "coverage", ".cache")


def tree_hash(repo, playbook_dir=None):
    """commit + hash of the working-tree diff + untracked files, ignoring the playbook folder and build/test caches
    (the gate itself writes logs there; they must not move the hash)."""
    rc, commit = sh(["git", "rev-parse", "--short", "HEAD"], repo); commit = commit.strip() if rc == 0 else "no-git"
    noise = list(NOISE)
    if playbook_dir:
        rel = os.path.relpath(os.path.abspath(playbook_dir), os.path.abspath(repo))
        if not rel.startswith(".."): noise.append(rel.rstrip("/") + "/")
    _, diff = sh(["git", "diff", "HEAD", "--", ".", *[f":(exclude){n.rstrip('/')}" for n in noise if n.endswith("/")]], repo)
    _, untracked = sh(["git", "ls-files", "--others", "--exclude-standard"], repo)
    sizes = []
    for f in untracked.split():
        if any(n in f for n in noise): continue
        p = os.path.join(repo, f)
        try: sizes.append(f"{f}:{os.path.getsize(p)}")
        except OSError: sizes.append(f"{f}:?")
    h = hashlib.sha256((diff + "\n" + "\n".join(sorted(sizes))).encode()).hexdigest()[:12]
    return commit, f"{commit}+{h}"


def parse_counts(out):
    for rx, pi, fi, si in COUNT_PATTERNS:
        m = re.search(rx, out)
        if m:
            g = lambda i: int(m.group(i)) if i and m.group(i) else 0
            return {"passed": g(pi), "failed": g(fi), "skipped": g(si)}
    return None


def first_failure(out):
    lines = out.splitlines()
    for i, l in enumerate(lines):
        if re.search(r"\b(FAIL|FAILED|Failed|Error|error TS|Exception|AssertionError|✗|✘|×)\b", l):
            return "\n".join(lines[max(0, i - 3): i + 22])
    return ""


def gate_cmds(pb, wp):
    d = os.path.join(pb, "work-packages")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.startswith(wp):
            md = open(os.path.join(d, f), encoding="utf-8").read()
            m = re.search(r"^##\s*Gate commands.*?$(.*?)(?=^##\s|\Z)", md, re.S | re.M | re.I)
            if m:
                return [l.strip().lstrip("-").strip().strip("`") for l in m.group(1).splitlines() if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("(")]
    return []


def latest_attempt(logs, wp):
    ns = [int(m.group(1)) for f in os.listdir(logs) if (m := re.match(rf"{wp}-gate-(\d+)\.json", f))] if os.path.isdir(logs) else []
    return max(ns) if ns else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wp"); ap.add_argument("--playbook-dir", required=True); ap.add_argument("--repo", default=".")
    ap.add_argument("--cmd", action="append", default=[]); ap.add_argument("--attempt", type=int, default=None); ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--verify", action="store_true"); ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    logs = os.path.join(a.playbook_dir, "logs"); os.makedirs(logs, exist_ok=True)

    if a.verify or a.show:
        n = a.attempt or latest_attempt(logs, a.wp)
        if not n: sys.exit(f"no gate summary for {a.wp}")
        summ = json.load(open(os.path.join(logs, f"{a.wp}-gate-{n}.json"), encoding="utf-8"))
        if a.verify:
            _, now = tree_hash(a.repo, a.playbook_dir)
            ok = now == summ["tree_hash"]
            print(f"{'MATCH' if ok else 'MISMATCH'}: log tree {summ['tree_hash']} · current tree {now}")
            if not ok: print("The log describes different code. Blocking finding; re-run the gate before reviewing further.")
            sys.exit(0 if ok else 2)
        print(json.dumps({k: v for k, v in summ.items() if k != "commands"}, indent=2))
        for c in summ["commands"]:
            print(f"\n$ {c['cmd']}\n  exit {c['exit']} · {c['duration_s']}s · tests {c['tests'] or '—'}" + (f"\n  first failure (log offset {c['log_offset']}):\n{c['first_failure']}" if c["first_failure"] else ""))
        return

    cmds = a.cmd or gate_cmds(a.playbook_dir, a.wp)
    if not cmds: sys.exit("no gate commands: pass --cmd or add a '## Gate commands' section to the WP file")
    n = a.attempt or latest_attempt(logs, a.wp) + 1
    logp = os.path.join(logs, f"{a.wp}-gate-{n}.log"); jsonp = os.path.join(logs, f"{a.wp}-gate-{n}.json")
    commit, th = tree_hash(a.repo, a.playbook_dir)
    started = datetime.now().isoformat(timespec="seconds"); t0 = time.time()
    results = []; overall = "PASS"
    with open(logp, "w", encoding="utf-8") as log:
        log.write(f"# {a.wp} gate attempt {n} · {started} · tree {th}\n")
        for cmd in cmds:
            log.write(f"\n$ {cmd}\n"); log.flush(); off = log.tell(); t1 = time.time()
            try:
                r = subprocess.run(cmd, cwd=a.repo, shell=True, capture_output=True, text=True, timeout=a.timeout)
                out, rc = r.stdout + r.stderr, r.returncode
            except subprocess.TimeoutExpired as e:
                out, rc = (e.stdout or "") + (e.stderr or "") + f"\n[timeout after {a.timeout}s]", 124
            log.write(out)
            res = {"cmd": cmd, "exit": rc, "duration_s": round(time.time() - t1, 1), "tests": parse_counts(out),
                   "first_failure": first_failure(out) if rc != 0 or (parse_counts(out) or {}).get("failed") else "", "log_offset": off}
            if rc != 0 or (res["tests"] and res["tests"]["failed"]): overall = "FAIL"
            results.append(res)
            if rc != 0: break  # later commands are meaningless after a failure
    _, th_after = tree_hash(a.repo, a.playbook_dir)
    _, patch = sh(["git", "diff", "HEAD"], a.repo)
    open(os.path.join(logs, f"{a.wp}-gate-{n}.patch"), "w", encoding="utf-8").write(patch)  # tree state for scoped re-reviews
    summ = {"wp": a.wp, "attempt": n, "started": started, "duration_s": round(time.time() - t0, 1), "commit": commit, "tree_hash": th,
            "tree_changed_during_run": th_after != th, "overall": overall, "commands": results, "log": os.path.relpath(logp, a.playbook_dir)}
    json.dump(summ, open(jsonp, "w", encoding="utf-8"), indent=2)
    print(f"{overall} · {a.wp} attempt {n} · {summ['duration_s']}s · tree {th} · summary {jsonp}")
    for c in results:
        print(f"  exit {c['exit']:>3} · {c['duration_s']:>6}s · tests {c['tests'] or '—'} · {c['cmd'][:70]}")
    if summ["tree_changed_during_run"]: print("WARNING: the tree changed while the gate ran — the log is not bound to one state; re-run.")
    print("Helpers: read the summary (--show); open the log only at a failing command's offset.")
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
