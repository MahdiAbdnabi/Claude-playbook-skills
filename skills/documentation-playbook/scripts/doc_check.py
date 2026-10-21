#!/usr/bin/env python3
"""
doc_check.py — the documentation playbook's mechanical check (the analogue of a gate): run once at the end of
every extraction phase and before Phase 5. Reports, per document and in total:
  - citations: every [src: File#Member] resolves to an existing file whose text contains Member
    (external citations such as [src: SPEC §3] or [src: owner-answer GAP-012] are counted separately, never failed)
  - untraced claims: body sentences carrying no tag at all (approximation)
  - hedging words outside code blocks (probably, likely, presumably, appears to, should, typically, usually, I assume, seems)
  - reconciliation: GAP/DRIFT ids used in documents vs rows in run-config.json; [rule: TBD] count; [PROTECTED] rules with a status
  - headers: document/lens header block + maturity line present
  - diagrams: every node/edge in diagrams/*.json has src or a gap/planned tag
Writes logs/check-<n>.json and logs/check-<n>.md stamped with the corpus tree hash (git), and registers the row in
run-config.json `checks` for the tracker. `--phase 3` (or later) makes a non-zero [rule: TBD] count blocking.

Usage:
    python3 doc_check.py DOCS_DIR --repo REPO [--config DOCS_DIR/_playbook/run-config.json] [--batch NAME] [--sample N] [--seed S]
    --sample N also writes logs/sample-<n>.json: N random resolvable citations with the cited member's surrounding text
    extracted (±12 lines), for the auditor to confirm without opening files itself.
Exit 0 when no unresolved citations and no hedges (unresolved/hedges are what block a checkpoint); 1 otherwise.
"""
import argparse, hashlib, json, os, random, re, subprocess, sys
from datetime import datetime

SRC_RX = re.compile(r"\[src:\s*([^\]]+)\]")
TAG_RX = re.compile(r"\[(src|GAP|DRIFT|PLANNED|PROTECTED|UNTESTED|tested|STALE|rule:\s*TBD|D\d)[^\]]*\]")
GAP_RX = re.compile(r"\[GAP-(\d{3})"); DRIFT_RX = re.compile(r"\[DRIFT-(\d{3})")
HEDGE_RX = re.compile(r"\b(probably|likely|presumably|appears to|should|typically|usually|I assume|seems)\b", re.I)
EXTERNAL_RX = re.compile(r"^(SPEC|ICD|owner-answer|DOC|ADR|DC)\b", re.I)
HEADER_KEYS = ("System:", "Scope:", "Version:", "Authority:")


def sh(cmd, cwd):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60); return r.returncode, r.stdout
    except Exception:
        return 1, ""


def tree_hash(repo):
    rc, commit = sh(["git", "rev-parse", "--short", "HEAD"], repo); commit = commit.strip() if rc == 0 else "no-git"
    _, diff = sh(["git", "diff", "HEAD", "--", ".", ":(exclude)docs", ":(exclude)_playbook"], repo)
    return f"{commit}+{hashlib.sha256(diff.encode()).hexdigest()[:10]}"


def strip_code(md):
    md = re.sub(r"```.*?```", "", md, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", md)


def split_header(md):
    lines = md.splitlines()
    if not lines or not lines[0].startswith("# "): return None, md
    i = 1; hdr = []
    while i < len(lines) and re.match(r"^(System|Scope|Version|Authority|Maturity[^:]*|Lens):", lines[i]): hdr.append(lines[i]); i += 1
    return hdr, "\n".join(lines[i:])


def resolve(cite, repo, cache):
    """[src: path/File.ext#Member] → (status, detail). status: ok | nofile | nomember | external."""
    c = cite.strip()
    if EXTERNAL_RX.match(c): return "external", c
    path, _, member = c.partition("#")
    path = path.strip(); member = member.strip()
    cands = cache.get(os.path.basename(path))
    if cands is None:
        cands = []
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "bin", "obj", "dist", ".venv", "venv", "__pycache__")]
            if os.path.basename(path) in files: cands.append(os.path.join(root, os.path.basename(path)))
        cache[os.path.basename(path)] = cands
    full = [p for p in cands if p.replace("\\", "/").endswith(path.replace("\\", "/"))] or cands
    if not full: return "nofile", path
    if not member: return "ok", full[0]
    for p in full:
        try: txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError: continue
        if member.split("(")[0] in txt: return "ok", p
    return "nomember", f"{full[0]}#{member}"


def member_excerpt(path, member, repo, n=12):
    try: lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError: return ""
    key = member.split("(")[0] if member else None
    idx = next((i for i, l in enumerate(lines) if key and key in l), 0)
    lo, hi = max(0, idx - n), min(len(lines), idx + n + 1)
    return "\n".join(f"{i+1:5d}  {lines[i]}" for i in range(lo, hi))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs"); ap.add_argument("--repo", required=True); ap.add_argument("--config", default=None)
    ap.add_argument("--batch", default=""); ap.add_argument("--sample", type=int, default=0); ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--phase", default="", help="phase that ran (3 or later makes [rule: TBD] blocking)")
    a = ap.parse_args()
    docs = a.docs.rstrip("/"); pb = os.path.join(docs, "_playbook"); logs = os.path.join(pb, "logs"); os.makedirs(logs, exist_ok=True)
    cfg = json.load(open(a.config or os.path.join(pb, "run-config.json"), encoding="utf-8")) if os.path.exists(a.config or os.path.join(pb, "run-config.json")) else {}
    files = []
    for root, dirs, fs in os.walk(docs):
        dirs[:] = [d for d in dirs if d not in ("_playbook", "_src")]
        files += [os.path.join(root, f) for f in fs if f.endswith(".md") and f not in ("TRACKER.md", "USAGE.md")]
    cache = {}; per_doc = []; unresolved = []; hedges = []; all_cites = []; gaps_used = set(); drifts_used = set(); tbd = 0; protected = []
    for f in sorted(files):
        md = open(f, encoding="utf-8").read(); hdr, body = split_header(md); rel = os.path.relpath(f, docs)
        text = strip_code(body)
        cites = SRC_RX.findall(text); statuses = {}
        for c in cites:
            st, detail = resolve(c, a.repo, cache); statuses[st] = statuses.get(st, 0) + 1
            all_cites.append({"doc": rel, "cite": c, "status": st, "detail": detail})
            if st in ("nofile", "nomember"): unresolved.append({"doc": rel, "cite": c, "reason": st})
        for m in HEDGE_RX.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            if not TAG_RX.search(text[max(0, m.start() - 160): m.end() + 160]) or True:
                hedges.append({"doc": rel, "line": line, "word": m.group(0), "context": text[max(0, m.start() - 60): m.end() + 60].replace("\n", " ")})
        sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n{2,}", re.sub(r"^\|.*$|^#+ .*$|^-{3,}$", "", text, flags=re.M)) if len(s.strip()) > 40]
        untraced = [s.strip()[:120] for s in sentences if not TAG_RX.search(s)]
        gaps_used |= set(GAP_RX.findall(md)); drifts_used |= set(DRIFT_RX.findall(md)); tbd += len(re.findall(r"\[rule:\s*TBD\]", md))
        for m in re.finditer(r"^.*\[PROTECTED\].*$", md, re.M):
            protected.append({"doc": rel, "line": m.group(0)[:140], "has_status": bool(re.search(r"\b(MATCH|DRIFT|NOT-IN-THIS-BATCH|NOT-YET-IMPLEMENTED|UNVERIFIED|PLANNED)\b", m.group(0)))})
        has_header = bool(hdr) and all(any(h.startswith(k) for h in hdr) for k in HEADER_KEYS[:2]); has_maturity = bool(hdr) and any(h.startswith("Maturity") for h in hdr)
        per_doc.append({"doc": rel, "claims_approx": len(sentences), "untraced": len(untraced), "untraced_examples": untraced[:3], "citations": statuses,
                        "hedges": sum(1 for h in hedges if h["doc"] == rel), "header": has_header, "maturity_line": has_maturity})
    # reconciliation
    cfg_gaps = {re.sub(r"\D", "", g.get("id", "")) for g in cfg.get("gaps", [])}; cfg_drifts = {re.sub(r"\D", "", d.get("id", "")) for d in cfg.get("drifts", [])}
    recon = {"gap_ids_in_docs_not_in_log": sorted(gaps_used - cfg_gaps), "gap_ids_in_log_not_in_docs": sorted(cfg_gaps - gaps_used),
             "drift_ids_in_docs_not_in_log": sorted(drifts_used - cfg_drifts), "drift_ids_in_log_not_in_docs": sorted(cfg_drifts - drifts_used),
             "rule_tbd": tbd, "protected_without_status": [p for p in protected if not p["has_status"]]}
    # diagrams
    diag = []; ddir = os.path.join(docs, "diagrams")
    if os.path.isdir(ddir):
        for f in os.listdir(ddir):
            if f.endswith(".json"):
                try: d = json.load(open(os.path.join(ddir, f), encoding="utf-8"))
                except Exception: diag.append({"file": f, "error": "unreadable"}); continue
                bad = [x.get("id") for x in d.get("nodes", []) + d.get("edges", []) if not x.get("src") and not ({"gap", "planned"} & set(x.get("tags", [])))]
                diag.append({"file": f, "elements": len(d.get("nodes", [])) + len(d.get("edges", [])), "untagged": bad})
    n = 1 + len([f for f in os.listdir(logs) if re.match(r"check-\d+\.json", f)])
    ok_cites = sum(1 for c in all_cites if c["status"] == "ok"); ext = sum(1 for c in all_cites if c["status"] == "external")
    summ = {"check": n, "batch": a.batch, "when": datetime.now().isoformat(timespec="seconds"), "tree_hash": tree_hash(a.repo), "documents": len(files),
            "citations": {"total": len(all_cites), "resolved": ok_cites, "external": ext, "unresolved": len(unresolved)},
            "untraced_claims": sum(d["untraced"] for d in per_doc), "hedges": len(hedges), "reconciliation": recon, "diagrams": diag, "per_document": per_doc,
            "unresolved_list": unresolved[:200], "hedge_list": hedges[:200],
            "blocking": bool(unresolved or hedges or recon["protected_without_status"] or any(dg.get("untagged") for dg in diag)
                             or (tbd and a.phase and a.phase[:1].isdigit() and int(a.phase[:1]) >= 3))}
    jp = os.path.join(logs, f"check-{n}.json"); json.dump(summ, open(jp, "w", encoding="utf-8"), indent=2)
    md = [f"# doc_check {n} · {summ['when']} · tree {summ['tree_hash']} · {'BLOCKING' if summ['blocking'] else 'clean'}",
          f"- documents {len(files)} · citations {len(all_cites)} (resolved {ok_cites}, external {ext}, **unresolved {len(unresolved)}**) · untraced claims {summ['untraced_claims']} · hedges {len(hedges)}",
          f"- reconciliation: rule:TBD {tbd} · GAP ids missing from log {recon['gap_ids_in_docs_not_in_log'] or '—'} · DRIFT ids missing from log {recon['drift_ids_in_docs_not_in_log'] or '—'} · [PROTECTED] without status {len(recon['protected_without_status'])}",
          "", "| Document | ~claims | untraced | resolved | unresolved | external | hedges | header | maturity |", "|---|---|---|---|---|---|---|---|---|"]
    for d in per_doc:
        c = d["citations"]; md.append(f"| {d['doc']} | {d['claims_approx']} | {d['untraced']} | {c.get('ok',0)} | {c.get('nofile',0)+c.get('nomember',0)} | {c.get('external',0)} | {d['hedges']} | {'✓' if d['header'] else '✗'} | {'✓' if d['maturity_line'] else '✗'} |")
    if unresolved: md += ["", "## Unresolved citations"] + [f"- {u['doc']}: `[src: {u['cite']}]` — {u['reason']}" for u in unresolved[:50]]
    if hedges: md += ["", "## Hedging words (rewrite with evidence or convert to [GAP])"] + [f"- {h['doc']}:{h['line']} “{h['word']}” — …{h['context']}…" for h in hedges[:50]]
    open(os.path.join(logs, f"check-{n}.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    cfg_path = a.config or os.path.join(pb, "run-config.json")
    if os.path.exists(cfg_path):  # register the row so the tracker's doc_check history needs no hand edit
        try:
            cfg.setdefault("checks", []).append({"check": n, "batch": a.batch, "date": summ["when"][:10], "tree_hash": summ["tree_hash"],
                                                 "citations_total": len(all_cites), "resolved": ok_cites, "unresolved": len(unresolved),
                                                 "hedges": len(hedges), "untraced": summ["untraced_claims"], "blocking": summ["blocking"]})
            json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        except Exception as e: print(f"warning: could not register check in {cfg_path}: {e}")
    if a.sample:
        rng = random.Random(a.seed); pool = [c for c in all_cites if c["status"] == "ok"]
        picks = rng.sample(pool, min(a.sample, len(pool)))
        for p in picks:
            path, _, member = p["cite"].partition("#"); p["excerpt"] = member_excerpt(p["detail"], member.strip(), a.repo)
        sp = os.path.join(logs, f"sample-{n}.json"); json.dump({"check": n, "tree_hash": summ["tree_hash"], "sample": picks}, open(sp, "w", encoding="utf-8"), indent=2)
        print(f"sample: {sp} ({len(picks)} citations with member excerpts for the auditor)")
    print(f"{'BLOCKING' if summ['blocking'] else 'clean'} · check {n} · citations {ok_cites}/{len(all_cites)} resolved ({ext} external, {len(unresolved)} unresolved) · untraced {summ['untraced_claims']} · hedges {len(hedges)} · rule:TBD {tbd}")
    print(f"summary: {jp}")
    sys.exit(1 if summ["blocking"] else 0)


if __name__ == "__main__":
    main()
