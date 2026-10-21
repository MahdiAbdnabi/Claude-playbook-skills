# Step Budgets, Harnesses & One Gate Run

Why: cost grows with **steps × context**, because every tool call re-reads the whole conversation so far. In a measured run, builders and reviewers took 30–80 tool calls each; the worst offenders were mutation sweeps done as hand edit/run/restore steps, five-minute gate logs pasted into context, and the builder, the coordinator and every reviewer each re-running the whole gate. The four rules below cut steps and context; each carries the guard that keeps it from hiding a failure.

## 1. Harness, not hand steps — with sentinels

The mutation sweep runs through `scripts/mutate.py`: the builder writes the **mutant list** (JSON: file, exact `find`, `replace`, the mutation point with `[src:]`, the narrow test command), the harness applies each mutant in a private `git worktree`, runs the tests, restores by construction, and writes one table to `logs/WP-NN-mutation.md`. The helper reads the table — one call instead of three per mutant.

**Guard — the harness is untested code judging test teeth.** A harness that runs against the real tree, or whose narrow test selection misses the one test that matters, reports *killed* for everything and nobody notices. So:
- Every run includes **two sentinels**: one mutant marked `expect: "killed"` (a line with an obvious test) and one marked `expect: "survived"` (a line known to have none). A sentinel whose result differs from its expectation **fails the harness** (exit 3) and the table is not used.
- A mutant that passes its narrow test run is re-run against the **full suite** (`--full-cmd`) before it is called a survivor; a kill by the full suite is recorded as "widen the narrow run", not as a survivor — otherwise narrow selection manufactures survivors and the builder writes tests for covered code.
- Mutants marked `guard: "environment"` are never removal candidates; the table says so on the row.
- The harness ships with the skill. Builders do not write their own (two did in the measured run; one of them was the WP that passed first time, which is why it is now here).

## 2. Summaries, not log tails

`scripts/gate.py` runs the gate commands once, writes the full output to `logs/WP-NN-gate-<n>.log`, and a **structured summary** `logs/WP-NN-gate-<n>.json`: per command → exit code, duration, test counts, the first failure block with context, and the log offset. Helpers read the summary (`gate.py WP-NN --show`) and open the log **only at a failing command's offset**. A tail of the last 40 lines is not enough: three commands in sequence and the one that failed is in the middle.

**Guard — what the summary does not carry.** Warnings, deprecations and slow-test signals in the middle of a log go unread by design. Phase 5 greps the run's logs once for a short pattern list (`warn|deprecat|flaky|retry`) and reports counts; nothing else reads full logs.

## 3. Per-stage call budgets — with a consistent stop

Each stage launch carries a tool-call cap from `run-config.json → budget.calls`, scaled by fidelity. Defaults:

| Stage | POC | MVP | Full | Notes |
|---|---|---|---|---|
| Design | 8 | 12 | 16 | reads the pack, writes the WP file |
| Build | 15 | 25 | 35 | includes one `gate.py` and one `mutate.py` call |
| Fix loop | 10 | 15 | 20 | incremental on the builder's conversation; findings in, targeted change, one gate run |
| Scoped re-review | 6 | 8 | 12 | prior findings + diff since + gate summary; escalates to Review on a blast-radius trigger |
| Review | 8 | 12 | 20 | High reviewer effort: +10 |
| Integrate | 4 | 6 | 6 | bookkeeping |

The cap is enforced from the orchestrator — a `max-turns` on the launch where the tool offers one, plus the helper reporting its own count in the handoff — because helpers do not count reliably mid-run.

**Guard — the cap must not make the honest step the first casualty.** Under pressure a builder skips the sweep, merges a dozen edits into one unreviewable write, or stops one call short of the gate. So the prompt states that **stopping at the cap with a clean handoff is a correct outcome**, and defines the stop: tests and code compile, nothing committed, a handoff note of *done / left / next command*, written to the WP file. The orchestrator then raises a Decision Card under the cost guard with three options — **continue with +N calls**, **split the WP**, **stop** — and a cap hit twice on the same WP recommends split. A stage that hits the cap *before* its single gate run gets the gate run by the orchestrator (one call) so the card carries evidence, not a guess.

## 4. One gate run per stage — bound to the tree

Build runs `gate.py` once and the log is stamped with the **tree hash** (commit + hash of the working-tree diff + untracked files). The coordinator does not re-run it. The reviewer's first action is `gate.py WP-NN --verify`: current tree hash against the log's.

**Guard — a green log can describe code edited afterwards.** A hash **mismatch is a Blocking finding** with nothing else to read; the gate is re-run before the review continues. The reviewer re-runs the gate itself only on these triggers, each named in the finding: hash mismatch; log older than the newest changed file; a `[tested:]` claim whose test name does not appear in the log; a mutant the reviewer re-applies (which runs in a worktree via `mutate.py`, not in the tree). A single run hides flakiness; the fix loops and Phase 5's one full re-run per run cover it.

## 5. What this changes in the stage prompts

- **Build:** write tests → fail-first evidence → implement → `mutate.py` with the mutant list (Standard/Tool-backed) → resolve survivors → `gate.py` once → read `--show`, not the log → build note with the call count. Cap-aware stop as above.
- **Verify:** `gate.py --verify` first → read the summary → the pack → re-apply three mutants via `mutate.py` → findings. No gate re-run except on the named triggers.
- **Fix loop:** continues the builder's conversation when it is still cached and under the size threshold (else a fresh fix helper with the pack + findings); findings in as facts → change → extend the mutant list for new conditionals → `gate.py` once (new attempt number) → note. Cap is incremental (+fix budget on the same conversation).
- **Re-review:** `build_context_pack.py WP-NN --scoped` decides scoped vs full by blast radius; scoped re-review confirms each prior finding by re-applying its mutant, diffs the tests, checks the diff under the lenses — one tier below the first review unless a trigger escalates it.
- **Orchestrator:** launches with the stage's cap; never re-runs a gate whose hash matches; records calls, tokens and attempt per launch in the session log; raises the cap card.

The tracker shows the budget per stage and, per session row, calls used against the cap, so the next run's defaults come from measurement rather than from this table.

## 6. Measured baseline these rules are judged against

One MVP run before any of §1–§4, `self-check.md` or the scoped re-review existed (web top-down shooter, 7 WPs, Recommended profile, Fully Automated): **$93–120** at list prices; ~85% of spend was helpers re-reading or loading context, under 2% was text written; 6 of 7 WPs failed their first review; builders and reviewers took 30–80 tool calls each; second reviews cost about as much as first. The estimated effect of the three changes together was $45–65 for the same run — an estimate from one run's token mix, not a measurement.

The tracker exists to turn that estimate into a measurement: first-review pass rate, calls per stage against the cap, review tokens first → re-review, fixes continued vs fresh, mutants listed/survived. After a run, compare its at-a-glance line with the numbers above; a change that does not move them is not pulling its weight and should be questioned, not kept out of habit.

One deliberate deviation from the original proposal: "log tails only (~40 lines)" became *structured summaries* (`gate.py` JSON, read via `--show`), because a tail of three sequential commands loses the one that failed in the middle; the cost effect is the same or better.
