# Execution Playbook — Core Methodology

Generic version of the gated development playbook. Bracketed slots (`[TASK]`, `[WP]`, `[STACK]`, `[LOCKED DECISIONS]`, `[LENSES]`) are filled per run from the intake and Phase 0.

**Contents**
1. Non-negotiable principles
2. Tagging protocol
3. Work-package anatomy and folder layout
4. Gates
5. Review lenses (summary — catalog in `review-lenses.md`)
6. The phases, with prompts
7. Decision rules for unattended execution
8. Model & effort guide
9. After the run: shape check, resuming, delta rounds
10. Templates

---

## 1. Non-negotiable principles

1. **Frame before building.** A task without a definition of done cannot pass a gate. Phase 0 writes the goal, the non-goals, the locked decisions and the acceptance criteria per work package before any code exists.
2. **Tests before code.** Acceptance tests are written from the criteria and fail first; the build makes them pass. A criterion that cannot be tested is a `[GAP]`, not a skipped test.
3. **Build in one context, attack in another.** The session that wrote the code has already convinced itself it is right. The reviewer is a fresh context with the code, the criteria and the lenses — and none of the builder's reasoning. The *fixer* need not be fresh: the independence the gate depends on is the reviewer's, so a fix continues the builder's conversation with the findings as facts, and a fresh reviewer checks the result.
4. **Gates decide, not opinions.** PASS/FAIL comes from the gate commands and the reviewer's verdict. Two fix loops, then `BLOCKED`. A gate is never weakened, a failing test never deleted, a threshold never lowered to pass.
5. **Gaps are truth.** A missing fact is a `[GAP]` with a one-line question. An invented default is a defect that surfaces three work packages later.
6. **Record why while you still know.** Non-obvious choices become ADRs at the gate; every decision — human or rule-driven — lands in `DECISIONS.md`. If it would have to be explained in a meeting, write it down now.
7. **Decide at boundaries, with the evidence in front of you.** A Decision Card at every phase boundary shows what was done, what the gate and reviewer found, the options, the recommendation, and the default if nobody answers.
8. **Pilot one work package before scaling.** The pattern is cheaper to fix on one WP than on eight.

---

## 2. Tagging protocol

Tags are grep-queryable; that is the point. Used in work-package files, ADRs, reviews, Decision Cards, code comments where useful, and commit messages.

| Tag | Means | Example |
|---|---|---|
| `[src: File.ext#Member]` / `[src: SPEC §3.2]` | The claim is backed by this location in code or spec. | `[src: RiskEngine.cs#Combine]`, `[src: ICD §4.1]` |
| `[GAP-###: question]` | Needed fact not available; nothing invented. Severity in GAPS.md. | `[GAP-007] Retry budget for IF-04 not stated — 3? configurable?` |
| `[DRIFT-###: A vs B]` | Two sources disagree (spec vs code, summary vs spec, builder vs reviewer). Both sides stated. | `[DRIFT-002] Spec says supervisor override; existing controller accepts officer.` |
| `[PLANNED]` | Intentionally deferred to a later WP; not a gap. | `[PLANNED] Fault-envelope handling → WP-05.` |
| `[UNTESTED: AC-##]` / `[tested: Class.Method]` | Whether an acceptance criterion has a passing test. | `[UNTESTED: AC-03]` is a gate failure unless `[PLANNED]`. |
| `[ADR-###]` | A recorded architecture/technical decision. | `[ADR-001] MiniSoap dispatcher over CoreWCF.` |
| `[DC-###]` | A Decision Card; `[DC-### AUTO rule 4]` when resolved by a decision rule. | `[DC-012 AUTO rule 4] simplest option that meets AC.` |
| `[RISK-###]` | A known risk with owner and trigger, in the risk register. | `[RISK-003] Redis single node in dev; prod topology differs.` |
| `[STALE]` | A criterion or citation whose source changed since it was written (delta rounds). | `[STALE] AC-02 — spec §3 changed 2026-10-09.` |
| `[BLOCKED]` | A work package that failed its gate after the fix loops. Run stops here. | `[BLOCKED] WP-04 — see DC-009.` |

---

## 3. Work-package anatomy and folder layout

A **work package (WP)** is the unit of building, gating and committing: small enough to design, build and verify in one sitting each, large enough to be worth a gate. Each has an id `WP-NN`, a name, dependencies, and a file:

```
_playbook/
  run-config.json          # source of truth: mode, format, lenses, WPs, stages, gates, cards, logs
  TRACKER.md / .html       # view of run-config
  USAGE.md / .html
  PLAYBOOK.md              # Phase 0 output: goal, DoD, locked decisions, non-goals, WP breakdown, gate toolchain
  CLAUDE.md (or AGENTS.md) # standing instructions every session reads: conventions, decision rules, folder layout
  work-packages/WP-NN-<name>.md   # Design output: scope, inputs, outputs, AC-## criteria, test list, gate commands, budget
  decisions/DC-###.md      # Decision Cards
  adr/ADR-###.md
  review/WP-NN-review.md   # reviewer verdicts, one per gate attempt
  DECISIONS.md  GAPS.md  RISKS.md
  logs/                    # session outputs (automated mode)
```

**WP file sections** (template §10.1): Goal · In scope / out of scope · Inputs · Outputs · Acceptance criteria `AC-##` (each testable, each later `[tested:]` or `[UNTESTED:]`) · Test list (written before code) · Gate commands · Lenses in force · Budget (max turns / max fix loops) · Depends on · Decision Cards raised.

---

## 4. Gates

A gate sits at the end of every WP's Verify stage. It passes only when all three hold:

1. **Gate commands pass** — the WP's listed commands (tests, lint, type-check, build, schema/coverage/fidelity checks as applicable). All deterministic; the list is written in Design, not improvised in Verify.
2. **Adversarial review returns PASS** — a fresh context checks the code against every `AC-##`, the active lenses, and the fidelity rules, trying to falsify at least five claims. It writes `review/WP-NN-review.md` with PASS/FAIL and numbered findings.
3. **Records exist** — every `AC-##` is `[tested:]` or `[PLANNED]`; the fail-first run is in the WP file; at Standard/Tool-backed self-check the mutation table is in the WP file and the restore check (`git diff --stat <snapshot>` = tests only) is among the gate commands; new ADRs written; GAPS/DECISIONS/RISKS updated; no hedging words (*probably, should, typically, assume*) left in WP docs without a tag.

On FAIL: findings → **fix by continuing the builder** (same conversation, findings appended as facts: a finding stands unless the fixer shows a test proving it wrong) → one gate run → **scoped re-review** by a fresh reviewer (§10.3b) unless a blast-radius trigger makes it a full review. **Max 2 fix loops.** Then `[BLOCKED]`, a Decision Card with the findings, run stops. A gate's thresholds can only change through an ADR and a Decision Card, before the gate runs.

The builder is continued only while that is actually cheaper: the orchestrator checks the session log — the Build ended within the cache window (same burst, no human pause) and the builder's conversation is under the size threshold in `budget` (default 150k tokens). Otherwise a **fresh fix helper** is launched with the builder pack plus the findings. The session log records which (`fix: continued` / `fix: fresh`). A fix loop's call cap is incremental on the continued conversation. A fix that weakens, narrows or deletes a test is Blocking at the re-review regardless of what else it resolved; a fix that adds a conditional extends the mutant list and the re-review re-applies the new mutants as well as the attempt-1 ones.

Phase 0 gate (**G0**): PLAYBOOK.md exists; every WP has at least one testable AC; dependency graph acyclic; gate toolchain runs green on the empty scaffold (WP-00); DC-000 decided.

---

## 5. Review lenses

The adversarial reviewer always applies **CORRECTNESS, SECURITY, MAINTAINABILITY, OPERABILITY**. Optional lenses (PERFORMANCE, UX, DATA, COMPLIANCE, COST, DOMAIN, …) and the shape for a custom one are in `review-lenses.md`. Each lens contributes concrete checks to the reviewer prompt (§10.3); the reviewer reports findings per lens so the Decision Card can show which perspective raised what.

---

## 6. The phases

Phase 0 once. Then, per WP in dependency order (pilot first): 1 Design → 2 Build → 3 Verify (gate) → 4 Decision Card & integrate. Phase 5 once all WPs are through 4. Phase 6 once.

### Phase 0 — Frame: goal, definition of done, work packages, pilot
**Tier:** strongest if the task touches protected rules or irreversible changes, else mid · effort high. **Output:** `PLAYBOOK.md`, `CLAUDE.md`, `run-config.json` with WPs, WP-00 scaffold, **DC-000**.

```
This is Phase 0 of the execution playbook for [TASK], target reachable at [ACCESS].
Confirmed summary (intent, not evidence; sources: [SUMMARY SOURCES]): [SUMMARY].
Expected outputs (each with where it lives and how it is checked): [EXPECTED OUTPUTS].
Stack (locked): [STACK]. Locked decisions: [LOCKED DECISIONS or "none beyond the stack"].
Fidelity: [POC | MVP | FULL]. Effort — logic: [L], architecture & solution design: [A],
UI design: [U or n/a]. Tooling: [Claude only | tool → purpose → WPs list].

1. Write the goal in one paragraph and the definition of done as a numbered list of
   observable outcomes, starting with the expected outputs verbatim. List non-goals
   explicitly; at POC fidelity, list everything deliberately skipped (validation, error
   paths, auth, concurrency, NFRs) once, as [PLANNED], with where a later level would put
   it. Every constraint you need but were not given is a [GAP-###] with a one-line
   question — do not pick a plausible value.
2. Inventory what is reachable: repo state, existing tests, CI, toolchain, specs, data.
   Each "needed but not reachable" is a standing [GAP].
3. Break the work into work packages WP-01..WP-NN by bounded responsibility, each with:
   goal, in/out of scope, inputs, outputs, 2–8 acceptance criteria AC-## phrased so a test
   can assert them, dependencies, gate commands, budget, the tool that produces each
   non-code output (from the tooling plan), and the lenses in force (POC: CORRECTNESS happy
   path only). WP-00 is always "scaffold and gate toolchain" so the gate runs green on an
   empty project before any feature. Size to fidelity: POC 1–3 WPs (WP-00 may be folded
   into WP-01), MVP the vertical slice, FULL the whole scope; do not force a round number.
   Where the effort allocation is I Am Too Rich on a dimension, add that dimension's extra
   work to the WPs it touches (design pass, exhaustive tests, NFR review) and budget for it.
4. Pick ONE pilot WP: small, depends only on WP-00, exercises the riskiest pattern
   (the integration, the invariant, the unfamiliar library) so the pattern is proven early.
5. Write CLAUDE.md: conventions, folder layout, the decision rules (§7) verbatim, how to
   update run-config and logs, "never weaken a gate".
6. Raise DC-000: options are (A) approve breakdown as proposed, (B) approve with listed
   changes, (C) re-frame. Include every [GAP] that blocks WP-01 as a question on the card.

Stop. Nothing is built until DC-000 is decided.
```

### Phase 1 — Design (per WP)
**Tier:** strongest for WPs touching protected/irreversible areas, else mid · effort high. **Output:** `work-packages/WP-NN-<name>.md` complete, test list, ADR candidates, **DC (Design→Build)**.

```
This is Phase 1 (Design) for [WP] — [NAME]. Read PLAYBOOK.md, CLAUDE.md, this WP's entry
in run-config, and the outputs of the WPs it depends on.

1. Confirm or refine the acceptance criteria AC-##; each must be assertable by a test.
   A criterion that cannot be tested becomes [GAP] + a question — never dropped silently.
2. Write the test list against the test budget for this run ([TEST BUDGET] — self-check.md §4):
   for each AC-##, the test name(s) that will prove it and the fixtures/data they need
   (missing data is [GAP]); for each guard, collector, observer, cap or detector the WP will
   add, one control test that drives the real function, naming the mutation that must make
   it fail and the fake clock/fixture it uses. If the plan exceeds the budget, raise a Decision
   Card (approve / trim / split the WP) rather than trimming silently.
3. Sketch the design: components touched, contracts, data shapes, error paths, how it
   fits the existing code [src:]. Where two viable approaches exist, write ADR-### with
   options and a recommendation — do not decide silently.
4. List the gate commands exactly as they will run, and the budget.
5. Raise the Design→Build Decision Card: summary, ADRs needing a call, [GAP]s blocking the
   build, options (proceed / proceed with changes / re-design), recommendation, and the
   default under the decision rules.

Stop at the card.
```

### Phase 2 — Build (per WP, tests first)
**Tier:** mid · effort high (small tier acceptable for pure boilerplate sub-steps). **Output:** failing tests → passing tests + implementation; self-check report.

```
This is Phase 2 (Build) for [WP]. The Design card is decided: [DECISION]. Stack: [STACK].
Your briefing is the builder pack (shared block, then the WP block): work within its fence and
read list; anything you need beyond it is a [GAP] with a one-line question, not a read.
Fidelity: [POC | MVP | FULL]. Effort — logic [L], architecture [A], UI [U]. Tools for this
WP's outputs: [TOOLS or "Claude only"]. Build exactly that much: a POC makes the happy path
run and lists what it skipped as [PLANNED]; an MVP applies the main validations; FULL adds
the non-functional ACs. If a listed tool is unavailable, stop with a [GAP] and a Decision
Card — do not hand-make its output.

1. Write the tests from the test list first. Run them; they must fail for the right reason
   (missing behaviour, not a typo). Paste the failing run into the WP file — that is the
   evidence, not the claim.
2. Implement the smallest change that makes them pass, following CLAUDE.md conventions
   and the existing code's patterns [src:]. No scope beyond the WP; anything discovered
   out of scope is [PLANNED] in a later WP or a [GAP].
3. Run the gate ONCE: `python3 scripts/gate.py [WP] --playbook-dir _playbook`. Read the summary
   (`--show`); open the log only at a failing command's offset. Fix what you can and re-run
   (new attempt number). Do not edit tests to pass them unless the test was wrong — and then
   say so in the WP file with the reason. Do not paste logs into your notes; cite the summary.
4. Self-check at level [SELF-CHECK]:
   - Minimal: every AC-## → [tested: …] or [UNTESTED: …]; hedging words removed or tagged;
     new ADRs drafted for any non-obvious choice; GAPS/RISKS updated.
   - Standard / Tool-backed, additionally (self-check.md §2–3): snapshot the tree; list every
     conditional, comparison, tolerance, fallback value, call order and cap you added, one
     row each with [src:] — as a mutant list (mutants.json: file, exact find/replace, point,
     narrow test command; include one expect:"killed" and one expect:"survived" sentinel; mark
     environment guards guard:"environment"); run `python3 scripts/mutate.py [WP] --mutants
     mutants.json --playbook-dir _playbook --full-cmd "<full suite>"`; read the table it writes
     (one call — never edit/run/restore by hand); a HARNESS FAILED result means the table is not
     usable, fix the mutant spec first; a survivor gets a test that kills it — remove code instead only with a written type/static argument,
     and never a guard on storage, network, clock, permissions, locale or platform (fake the
     environment and test it). The harness never touches the real tree; `git status` must show
     only your own changes afterwards (this is a gate command). Every detector has a control test through the real
     path with a fake clock where time is involved; soak/fuzz/property tests assert they ran
     the live path. Put the mutation table in the WP file. Tool-backed: run the mutation tool
     on the changed files and record kill rate and survivors.
5. Write a build note: what changed, what you are least sure of (the reviewer starts
   there), which decision rules you applied with [DC-### AUTO rule n] if any, and the number
   of tool calls you used.

Call budget: [CALL CAP] tool calls for this stage. Stopping at the cap with a clean handoff is
a correct outcome: tests and code compile, nothing committed, and a "done / left / next
command" note in the WP file. Do not skip the sweep or the gate to fit the cap — stop and say so.
Stop. Do not run the review yourself.
```

### Phase 3 — Verify (gate + adversarial review, fresh context)
**Tier:** strongest · effort xhigh for the review; gate commands are deterministic. **Output:** `review/WP-NN-review.md` PASS/FAIL with findings; fix loops; gate result in run-config.

Reviewer prompt: §10.3. Runner logic:

```
Build already ran gate.py once (summary + tree hash in logs/). Orchestrator: `gate.py --verify`;
MISMATCH → re-run gate.py (one call), then continue. Summary overall FAIL → FAIL (findings = summary)
reviewer effort NONE → record `review: none`, PASS on commands alone, proceed (Phase 5 lists these gates)
else build packs (build_context_pack.py WP-NN --gate-log … --least-sure …) → spawn reviewer with
  packs/shared.md FIRST then packs/WP-NN-reviewer.md (fresh context; model/effort = resolved "3") → PASS?  no → FAIL (findings)
FAIL and fix_loops < 2 → fix: continue the builder's conversation (findings as facts; model/effort = resolved "3fix")
  if cached & under size threshold, else fresh fix helper with builder pack + findings → one gate.py run →
  re-review: build_context_pack.py --scoped → full_review_required?  no → scoped re-review (§10.3b; model/effort = resolved "3re")
                                                                      yes → full review (§10.3; resolved "3") → fix_loops++ → repeat
call cap hit at any stage → clean handoff → Decision Card (continue +N / split WP / stop) under the cost guard
FAIL and fix_loops == 2 → mark [BLOCKED], raise Decision Card with all findings, STOP RUN
PASS → record gate result, proceed to Phase 4
```

### Phase 4 — Decision Card & integrate (per WP)
**Tier:** mid · effort medium. **Output:** commit (if git), updated logs, **DC (Verify→next)**, tracker regenerated.

```
This is Phase 4 for [WP], gate PASSED on attempt [n]. 
1. Finalise ADRs raised in this WP; move DECISIONS/GAPS/RISKS entries from draft to final.
2. If the target is a git repo: commit "WP-NN: <name> (PASS)" with the gate summary in the body.
3. Raise the Verify→next Decision Card: evidence (gate output summary, reviewer findings
   accepted vs deferred), what the next WP in order is, options (proceed to next / re-order /
   pause for the open gaps listed), recommendation, default.
4. Regenerate the tracker; set next action.
Stop at the card (User Monitored) or resolve by rule and continue (Fully Automated).
```

### Phase 5 — Final audit (once, strongest tier, fresh context)
**Output:** audit table + traceability check.

```
This is Phase 5, all WPs are through Phase 4. In a fresh context:
1. Table: AC-## | WP | test [tested:] | gate attempt that passed | reviewer finding ids |
   status (MET / MET-WITH-DEFERRED / UNMET). No prose "done" anywhere.
2. Traceability: every definition-of-done item in PLAYBOOK.md → at least one AC-## → at
   least one passing test. List any DoD item without that chain.
3. Decision audit: every [DC-### AUTO rule n] — was the rule applied correctly? List the
   ones a human should re-check (irreversible, cost, or where rule 4 "simplest" was used
   on a design choice).
4. Citation sample: 15 random [src:] tags across WP files and ADRs; re-open each; report
   hits/misses. Plus three mutation-table rows across the run: re-apply, confirm the named
   test fails, restore.
4a. Log scan: grep the run's gate logs once for `warn|deprecat|flaky|retry` and report counts
   per WP — the only full-log read in the run.
4b. Review cost: average tokens of first reviews vs re-reviews (from the session log), and
   how many re-reviews were scoped vs full with the trigger that forced each full one.
4c. First-review pass rate for the run (WPs whose first gate attempt passed review / WPs
   gated), with the failing WPs' finding classes (mechanical vs conceptual).
5. Residuals: open GAPs by severity, open RISKs, [PLANNED] items with their target WP.
Stop and report. Below 90% citation hits or any UNMET DoD item → recommend which WP to re-open.
```

### Phase 6 — Handover (once)
**Tier:** mid · effort high. **Output:** README/runbook updates, CHANGELOG, "next run" notes, final tracker + usage guide.

```
This is Phase 6. Produce what the next person (or next run) needs: how to run, test and
deploy what was built [src:]; what was decided and why (link ADRs and DCs, do not repeat
them); what is [PLANNED] and [GAP]; how to start a delta round when the spec changes.
Regenerate the tracker and usage guide as final.
```

---

## 7. Decision rules for unattended execution

Written into `CLAUDE.md` so an automated run applies them instead of asking; every application is recorded `[DC-### AUTO rule n]`.

1. **The spec wins.** If the spec/docs and this playbook conflict on a fact, follow the spec and log the conflict in DECISIONS.md.
2. **Never invent.** A missing fact becomes `[GAP]`; continue on what is known.
3. **Contradictions become `[DRIFT]`**, presented both ways; never resolved silently.
4. **Ambiguous technical choices:** pick the simplest option that satisfies the acceptance criteria; log one line of reasoning. (Phase 5 re-checks every use of this rule.)
5. **Never weaken a gate.** If a gate cannot pass without inventing, mark the WP `[BLOCKED]` and stop.
6. **No dependencies beyond the locked stack**, except dev-only tooling a gate needs, logged.
7. **Irreversible actions stop the run** (destructive migrations, deleting data, publishing, external side effects) — a Decision Card waits for a human in every mode.
8. **Budget stops the run**: a card whose options differ in cost beyond the stated budget, or a WP exceeding its max-turns budget twice, waits for a human.
9. **Commit per passed WP** (git targets): `WP-NN: <name> (PASS)`.

---

## 8. Model & effort guide

Tiers are `small` (Haiku) → `mid` (Sonnet) → `strong` (Opus) → `top` (Fable); efforts `low → medium → high → xhigh → max`. This table is the **Recommended** profile; the user's cost profile shifts it (`cost-and-orchestration.md §2`) and the tracker shows recommended, resolved and actually-used side by side.

| Phase | Nature of work | Tier | Effort | Critical |
|---|---|---|---|---|
| 0 Frame | judgement over the whole task | mid; **strong** if the task touches protected or irreversible areas | high | when strong |
| 1 Design | per-WP judgement | mid; **strong** for WPs touching protected/irreversible areas | high | when strong |
| 2 Build | volume, mechanical with local judgement | mid (small for boilerplate sub-steps) | high | — |
| 3 Verify — review | adversarial, highest stakes, fresh context | **strong** | xhigh | **yes** |
| 3 Verify — fix loop | targeted; continues the builder | mid | high | — |
| 3 Verify — scoped re-review | fresh context; attempt-1 findings + diff since + gate summary | one tier below review (floor mid) | high | escalates to the review tier on any blast-radius trigger |
| 4 Integrate | bookkeeping | small | medium | — |
| 5 Audit | the evidence acted on, fresh context | **strong** | xhigh | **yes** |
| 6 Handover | synthesis | mid | high | — |

**Critical** phases floor at `mid`/`medium` under Very Low Budget and are the first to move to `top` under I Am Too Rich. The per-WP upgrade for Phases 0/1 is set in the config's `models` block when Phase 0 flags the WP (`"critical": true` on that WP's design entry). Tier → model name is a run-time mapping; the orchestrator passes the resolved tier's name as the subagent's `model` and the resolved effort as its `effort`; the reviewer and auditor get a **new** agent, never the builder's. In a single-model session, tier collapses to effort.

**Step budgets (`step-budgets.md`):** every launch carries its stage's call cap (`budget.calls`, scaled by fidelity) via `max-turns` where available; the session log records calls and tokens per launch; a cap hit produces a clean handoff and a Decision Card. The orchestrator never re-runs a gate whose tree hash matches the latest summary.

**Runner notes (headless):** one WP stage per `claude -p` session, driven by a loop over run-config in dependency order; resumable from the config; logs to `_playbook/logs/`; a permission mode with an explicit allow-list rather than bypass; flags verified against `claude --help` before the first run. The skill's Fully Automated mode is the in-session equivalent: subagents instead of sessions, run-config instead of a state file.

---

## 9. After the run

### 9.1 Pilot shape check (after the pilot WP's Phase 4)
Before scaling: were all ACs testable as written; did tests fail first for the right reason; did the sweep kill anything (zero survivors on a pilot is suspicious — a short list or unusually good tests; look before trusting it); did the reviewer find at least one real issue (if zero, the lenses or the reviewer prompt are too weak — fix before trusting later PASSes); did the reviewer's re-applied mutants reproduce; did the gate commands catch anything the self-check missed; was the Decision Card answerable in one line; did the pilot pass review first time, and if not, which class the findings were (mechanical → strengthen the sweep; conceptual → the reviewer is doing its job). Fix the pattern, not the pilot.

### 9.2 Resuming
Read run-config + tracker. Resume at "next action" in the recorded mode. Answered cards → apply, log, continue. `[BLOCKED]` WP with new input → fix session with counter reset, input recorded on the card. Never re-run a passed WP's build on resume; re-run its gate only if its inputs changed.

### 9.3 Delta round (spec or upstream change after the run)
1. Diff the spec/inputs since the run's recorded ref; list changed items.
2. Grep WP files, ADRs and DECISIONS for `[src:]` into changed items; tag `[STALE]`.
3. Re-run Phase 1 on WPs with stale ACs; re-run Phase 3 (gate + review) on them and on every WP downstream in the dependency graph.
4. New scope → new WPs appended, pilot rule does not re-apply unless the pattern changed.
5. Phase 5 again over touched WPs; tracker's delta log updated.

---

## 10. Templates

### 10.1 Work-package file
```
# WP-NN — <name>
Depends on: WP-.. | Pilot: yes/no | Budget: <max turns> turns, 2 fix loops
Fidelity: POC | MVP | FULL · Effort: logic <L> / architecture <A> / UI <U>
Tools: <tool → output it produces, or "Claude only">
## Goal
## In scope / Out of scope
## Inputs                (files, specs, prior WP outputs — each [src:])
## Outputs
## Acceptance criteria
AC-01 <observable, assertable statement>            → [tested: …] | [UNTESTED: AC-01] | [PLANNED]
AC-02 …
## Test list             (written before code; one line per test: name — proves AC-##)
## Gate commands         (exact commands, in order)
## Lenses in force       (defaults + extras)
## Decision Cards raised (DC-###)
## Fail-first evidence   (Phase 2: the failing test run, pasted, before implementation)
## Mutation table        (Phase 2, Standard/Tool-backed: # | point [src:] | mutant | test that failed | resolution; tool kill rate if used)
## Build note            (Phase 2: what changed, least-sure areas, rules applied)
## Gate history          (attempt n: commands PASS/FAIL, review PASS/FAIL, findings ids)
```

### 10.2 ADR
```
# ADR-### — <decision in one line>
Status: Proposed | Accepted (DC-###) | Superseded by ADR-###
Context:  <why a decision is needed; what constrains it [src:]>
Options:  1. … 2. … 3. …   (each: consequence, cost, reversibility)
Decision: option n
Consequences: <what we gain, what we give up, what becomes [UNTESTED]/[PLANNED]/[RISK]>
```

### 10.3 Adversarial reviewer prompt (fresh context)
```
You are reviewing [WP] — [NAME]. Your briefing is the reviewer pack you were given (shared
block, then the WP block): acceptance criteria AC-##, gate output, changed files and diff,
lens checks, and — at Medium/High effort — the quoted contracts, dependent ADRs, the builder's
least-sure hints and an on-demand read list (High: the whole playbook folder and repo).
Do not read beyond your pack's scope; if a claim cannot be checked within it, say so as a
finding rather than guessing. You do NOT have the builder's reasoning, and you should not
trust the build note's claims — verify them.

First action: `python3 scripts/gate.py [WP] --playbook-dir _playbook --verify`. A tree-hash
MISMATCH is a Blocking finding — stop and report it; the log describes different code. Then
read the gate summary (`--show`), not the log; open the log only at a failing offset. Do not
re-run the gate except on these triggers, each named in a finding: hash mismatch; log older
than the newest changed file; a [tested:] claim whose test name is absent from the log; a
mutant you re-apply (via mutate.py in a worktree, never in the tree). Call budget: [CALL CAP].

Your job is to FAIL this work package if you can. Attempt to falsify at least five claims:
pick the ACs and the build note's "least sure" items first.

For each lens, run its checks and record findings as:
  F-## | lens | severity (Blocking/High/Low) | what is wrong | evidence [src:] | AC affected
Lenses in force: [LENSES — paste the checks from review-lenses.md]

Then:
- Confirm each AC-## has a passing test that actually asserts it (open the test; a test
  that cannot fail is a Blocking finding).
- Confirm no gate command, test or threshold was weakened since the Design (diff them).
- If the WP file has a mutation table: re-apply three mutants (the two you judge most likely
  wrong and one at random) and confirm the named test fails; a mutant that does not reproduce
  is a High finding against the table, an obvious mutation point missing from it is a High
  finding against the sweep. Restore before writing the review.
- Hedging words in WP docs without a tag → Low finding each.

Verdict: PASS only if zero Blocking and zero High findings. Write review/WP-NN-review.md
with the verdict, the findings table, and the five falsification attempts and their result.
```

### 10.3b Scoped re-review prompt (attempt 2+, fresh context, when no blast-radius trigger fired)
```
You are re-reviewing [WP] — [NAME], attempt [n]. Your briefing is the scoped reviewer pack:
the shared block, the acceptance criteria, the attempt-[n-1] findings, the diff since
attempt [n-1] (changed files and hunks only), the latest gate summary, the mutation table
rows added since, and the lens checks. You have NOT seen the builder's reasoning.

First action: `python3 scripts/gate.py [WP] --playbook-dir _playbook --verify` — a tree-hash
MISMATCH is Blocking. Then:
1. For each attempt-[n-1] finding: re-apply its mutant (or re-run its failing check) through
   mutate.py in a worktree and confirm it is now killed / resolved by a test that asserts the
   behaviour — not by a narrowed or deleted test. Status per finding: RESOLVED / NOT RESOLVED /
   RESOLVED BY WEAKENING (Blocking).
2. Diff the test files since attempt [n-1]: any assertion removed, loosened, skipped or
   special-cased for the reviewer's input is Blocking.
3. Re-apply every mutant added to the table since attempt [n-1].
4. Run the lens checks on the diff only. A new High anywhere in the diff is a finding.
5. If while doing this you see the diff touches a file outside the WP's fence, a quoted
   contract, or more than a third of the WP's files — or you notice a new Blocking/High
   problem OUTSIDE the diff — stop and report "full review required" with the reason and the
   finding. Never PASS a package on which you have seen a High you were not scoped to check.
Verdict: PASS only if every prior finding is RESOLVED, no new Blocking/High, and no weakening.
Write review/[WP]-review-[n].md with the per-finding table and the mutant re-application log.
Call budget: [CALL CAP].
```
Blast-radius triggers that force a **full** review instead (computed by `build_context_pack.py --scoped`, each named in the pack): the diff touches a file outside the WP's fence; it touches a contract quoted in the pack; it touches any test file by deletion or by reducing assertions; more than a third of the WP's files changed; an attempt-[n-1] finding was Blocking/High on SECURITY, COMPLIANCE or DOMAIN; the WP touches a `[PROTECTED]` rule; this is attempt 3 (findings persisted through a loop); or the scoped reviewer itself reports a new Blocking/High outside the diff. A full review keeps the first-review model tier. Phase 5 remains a fresh full pass over the whole run, so anything a scoped review missed still has a backstop.

### 10.4 DECISIONS.md entry
```
- DC-### | <date> | <WP> | <decision in one line> | by: <person> | AUTO rule n | ADR-### | reversible: yes/no
```

### 10.5 GAPS.md entry
```
[GAP-###] <one-line description>
Severity: Blocking | High | Low      Found in: WP-NN, Phase n
Blocks: <what cannot proceed>        Question: <one line answerable in one line>
Answered by / on: —
```

### 10.6 RISKS.md entry
```
[RISK-###] <risk>  | likelihood/impact | trigger to watch | mitigation or [PLANNED] WP | owner
```
