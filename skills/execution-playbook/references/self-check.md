# Build Self-Check & Test Budget

Why this exists: in a measured run, 6 of 7 work packages failed their first adversarial review, and the High findings were almost all of one kind — code no test could catch (a guard that missed a branch, a watch window no test exercised, a test that passed whether or not the behaviour existed). Each failure cost a fix helper and a second strong-tier review, so most packages were built and checked twice. Once a self-mutation sweep was added to Build mid-run, the next package passed first time and the rest failed with one High instead of two. The self-check makes that standard from the first package, and the test budget stops Design from planning 117 tests for a pilot.

The self-check is the builder checking its own tests' teeth. It is **not** a substitute for the reviewer: it removes the mechanical class of findings ("no test could catch this"), not the conceptual class (wrong contract, wrong rule). Reviewer effort is chosen separately and is not lowered because the sweep exists.

## 1. Self-check level — asked before the run

| Level | What Build does before reporting | Cost per Build | What you give up |
|---|---|---|---|
| **Minimal** | Fail-first evidence only: the failing test run is pasted into the WP file before the implementation is written. | ~0 extra | The sweep. Expect the first-review failure pattern above. Default for a Fastest POC. |
| **Standard** (recommended; default for MVP and Full) | Fail-first evidence **+ hand mutation sweep with a mutation table + detector control tests + restore check** (§2–§4). | roughly +20–40% Build tokens and time; typically less than one fix loop plus one re-review | The objectivity of a tool: the builder lists the mutants it thought of. The reviewer re-applies a sample to keep the table honest. |
| **Tool-backed** | Standard **+ a mutation-testing tool** (Stryker for JS/TS and .NET, mutmut for Python, PIT for Java, cargo-mutants for Rust — set up in WP-00) run as a gate command, scoped to the WP's changed files, with a kill-rate threshold recorded in the WP file (default 80%; survivors listed). | +WP-00 setup; +minutes per gate run (mutation tools are slow — scope to the diff, never the repo) | Little. The hand sweep still covers what tools mutate poorly (call order, fallback values, environment guards). Choose this when the stack has a tool and the fidelity is Full or the WP touches `[PROTECTED]` rules. |

Record as `self_check`. It can be raised mid-run for stages not yet started (logged as a decision); lowering it mid-run is a Decision Card, because it changes what later gates prove.

## 2. The mutation sweep (Standard and Tool-backed)

The sweep runs through `scripts/mutate.py` (`step-budgets.md §1`): the builder writes the mutant list, the harness applies each mutant in a private worktree, runs the tests, and writes the table; sentinels fail the harness if its results are wrong. Before writing the build note, the builder:

1. **Lists** every conditional, comparison, tolerance, fallback value, call-order dependency and cap the package added or changed — one row each in the **mutation table** in the WP file, with `[src: file#member]`.
2. **Mutates** each one (flip the condition, shift the boundary, change the fallback, swap the order, remove the cap), runs the tests, and records which test failed. A mutant with no failing test **survived**.
3. **Resolves** every survivor by writing the test that kills it. Removing the code instead is allowed only when unreachability is shown by a **type or static argument** written in the table, never by the absence of a test — and never for guards on environment conditions (storage, network, clock, permissions, locale, platform). Those are exactly the branches tests don't reach and production does; a survivor there always gets a test with the environment faked. A removal is logged as a decision.
4. **Restores** by construction — the harness never edits the real tree. The gate includes `git status --porcelain` showing only the builder's own changes; a stray worktree or patch is a FAIL on commands, not a reviewer finding.
5. **Soak, fuzz and property tests assert they ran the live path** — a counter, a trace or an observable side effect of the real function — not merely that N iterations completed.

The table's shape:

```
| # | Mutation point [src:] | Mutant applied | Test that failed | Resolution |
| 1 | RiskEngine.cs#Combine `worst >= current` | `>` | RiskEngineTests.TiesKeepWorst | killed |
| 2 | storage.ts#safeGet `if (window.localStorage)` | removed guard | — survived | added SafeGetSpec.NoStorage (env faked) |
| 3 | watcher.ts#window `cap = 50` | `cap = 51` | — survived | static: cap only read by the test-visible path? NO — added WatcherSpec.CapAt50 |
```

## 3. Detectors proven through the real path

Every guard, collector, observer, cap or detector the package adds gets a **control test** that drives the same function the gate or runtime uses — not a helper that reimplements it. The Design test list names, for each control, the **mutation that must make it fail** (that row then appears in the mutation table, pre-filled). Time-based detectors (windows, debounces, timeouts) use a fake clock injected through the real code path; sleeps are a Low finding. Control tests count inside the test budget (§4), so Design prioritises rather than pads.

## 4. Test budget — derived, not asked

The budget is computed from fidelity and the Logic effort; Design plans against it and raises a **Decision Card** when the plan exceeds it ("N planned against a budget of M — approve, trim, or split the WP"). It is a sanity check on *planning*, not a gate on count: a builder that merges assertions to hit a number has defeated it, so the reviewer's CORRECTNESS check "each AC has a test that can fail" is what actually holds.

| | Per AC | Per implied edge case | Per detector | End-to-end | Expected per WP (unit / e2e) |
|---|---|---|---|---|---|
| **POC** (Logic Very Low) | 1 smoke | 0 | 0 | ≤ 1 per flow | ≤ 10 / ≤ 3 |
| **MVP** (Logic Recommended) | 1–3 | 1 | 1 control | ≤ 2 per flow | 15–40 / ≤ 10 |
| **Full** (Logic Recommended) | 2–3 | 1–2 | 1 control | ≤ 2 per flow | 30–80 / ≤ 15 |
| **Logic I Am Too Rich** (any fidelity above POC) | property-based or table-driven per rule | all enumerated | 1 control + adversarial input | ≤ 3 per flow | no upper bound; the plan still lists every test and its AC |

A WP that needs more than the budget is usually two WPs. The card's "split" option is there for that reason.

## 5. Reviewer and audit hooks

- The reviewer pack (every effort level above None) includes the mutation table. The reviewer **re-applies three mutants** from the table — the two it judges most likely to be wrong and one at random — and confirms the named test fails. A mutant that does not reproduce is a High finding against the table; a table missing an obvious mutation point is a High finding against the sweep.
- The tracker records per gate: mutants listed / survived / tests added, and whether the WP **passed review on the first attempt**. The at-a-glance line shows the run's **first-review pass rate** — the number this whole mechanism exists to move; compare it against the pilot and against earlier runs.
- The pilot shape check asks: did the sweep kill anything? Zero survivors on a pilot is suspicious, not reassuring — either the list was too short or the tests were already unusually good; look before trusting it.
- Phase 5 samples three mutation-table rows across the run alongside the citation sample.
