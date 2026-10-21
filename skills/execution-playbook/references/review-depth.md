# Reviewer Effort & Context Packs

The adversarial reviewer is the most expensive agent in the run and the one whose cost varies most with how it is briefed. Left to a reading list (PLAYBOOK.md, CLAUDE.md, every ADR, earlier WP files and reviews, the repo) a reviewer has been observed loading 150–360k tokens before checking anything. **Reviewer effort** is a pre-run choice that sets how the reviewer is briefed and how far it looks; it is asked with the cost and the effect on the output stated, because the trade is real in both directions.

## 1. The four levels

| Level | What the reviewer receives | What it does | Typical input per review* | What you give up |
|---|---|---|---|---|
| **None** | — | No independent review. The gate is **gate commands + the builder's self-check only**. Every gate record says `review: none`; the tracker counts gates passed without independent review; Phase 5 lists them. | 0 | The core guarantee of the playbook. Confident-but-wrong builds pass if the tests they wrote pass. Only defensible for a Fastest POC or a throwaway spike; the skill warns once when chosen with MVP or Full. |
| **Low** | A **minimal pack**: the ACs, the changed-file list with the diff, the gate output, the lenses' check lists. No contracts, no ADRs, no repo access beyond the diff. | Confirms each AC has a test that asserts it and can fail; reads the diff against the AC wording; runs the CORRECTNESS checks and whichever other lens checks the diff alone can answer. Does not attempt to falsify claims it cannot see the evidence for. | ~5–10k | Findings about how the change fits the rest of the system (a contract broken elsewhere, a duplicated rule, a convention violated) — the reviewer cannot see "elsewhere". MAINTAINABILITY and OPERABILITY findings drop to what the diff shows. |
| **Medium** (recommended) | A **context pack** (§2): a fixed shared block (cached), then a reviewer block with the ACs, the contracts the WP touches quoted with `[src:]`, the ADRs it depends on (summaries with ids), the changed files and diff, the gate output, the build note's "least sure" items as hints, the lens checks, and an **on-demand read list** of files it may open with a reason. | Everything Low does, plus the five falsification attempts against the quoted contracts and decisions, and targeted reads from the on-demand list when a claim needs checking. | ~15–30k, of which the shared block (~3–6k) is a cache hit after the first launch | Discoveries outside the pack and the read list. The coordinator's selection is the ceiling on what the reviewer can notice; the pilot shape check asks whether the reviewer lacked anything, and the pack template is fixed if so. |
| **High** (full reading) | The pack **plus** unrestricted access: PLAYBOOK.md, CLAUDE.md, all ADRs, earlier WP files and reviews, the whole repository. | Everything Medium does, plus free exploration: it can find the convention nobody quoted, the earlier review finding that recurs, the contract three modules away. | ~80–360k depending on repo size; no meaningful cache reuse beyond the shared block | Cost and time. Mostly cost: at this level one review can exceed the WP's build. |

\* Order-of-magnitude input tokens per review attempt; multiply by gate attempts (up to 3 with the two fix loops) and by WPs. Output tokens are similar across levels. The figures are there so the choice is informed, not precise — the tracker's session log records what each review actually consumed, and after the pilot the orchestrator reads the real number back.

**Defaults:** Low for a Fastest POC, Medium for MVP and Full. High must be chosen explicitly. **None** is accepted at any fidelity but marks every gate and triggers a one-line warning at MVP/Full. The level can be changed mid-run for stages not yet started (recorded as a decision) — a common pattern is Medium for the pilot and the plain WPs, High for the one WP that touches a `[PROTECTED]` rule.

**Interaction with the cost profile:** the cost profile picks the reviewer's *model tier* (strong under Recommended, Sonnet floor under Very Low Budget); reviewer effort picks *how much it is given to read*. They multiply: High effort under I Am Too Rich is the most expensive combination the skill offers, and the skill says so when both are chosen.

## 2. Context packs

Packs are built by `scripts/build_context_pack.py` at **launch time** for the stage being launched — never pre-built for the whole run, because WP-02's gate can change a contract WP-03's pack quotes. Three files per launch under `_playbook/packs/`:

```
packs/shared.md              # immutable for the run; byte-identical on every launch; goes FIRST
packs/WP-NN-builder.md       # the builder's block
packs/WP-NN-reviewer.md      # the reviewer's block — built separately, not from the builder's pack
```

**Shared block (cacheable).** Only things that cannot change during the run: the seven principles, the tagging protocol, the decision rules, the locked decisions, the stack, the conventions excerpt from CLAUDE.md, the repo map (top-level tree with one line per folder). Nothing dated, no status, no "next action". The script hashes it and refuses to regenerate it with different content unless `--rotate-shared` is passed (which is itself a logged decision, because it invalidates the cache). Prompt caching matches an exact prefix, so this block is placed first in every helper prompt, before anything per-WP; launches in the same burst (independent WPs at the same stage, builder then reviewer) reuse it at the cached-read price.

**Builder block.** The WP file's goal, scope, ACs and test list; the contracts it touches, quoted verbatim with `[src: file#member]`; the ADRs it depends on, as id + decision + consequence; the open GAPs and DRIFTs that touch it; the tool assignments; **files it may change** (the fence) and **files it may read on demand** (the valve); the id ranges it may allocate for new GAP/DRIFT/ADR entries so collects do not collide. The rule in the block: *do not read beyond the pack and its read list; if you need more, say what and why as a `[GAP]`* — the gaps-are-truth stance applied to context. Needing a file outside the fence is a `[GAP]` and a Decision Card, not an edit and not a silent stop.

**Reviewer block.** Opens with the latest gate summary (`logs/WP-NN-gate-<n>.json`: overall, per-command results, tree hash) and the instruction to `gate.py --verify` before anything else; the full log is never in the pack. Includes the WP file's fail-first evidence and mutation table at every level above None, with the instruction to re-apply three mutants (`self-check.md §5`). Built from the WP file, the diff and the gate log — not from the builder's block or its reasoning, so the reviewer's framing stays independent. Contents by level are in §1. At Medium and High it includes the five-attempt falsification instruction from `playbook-core.md §10.3` and the lens checks for the lenses in force.

**Everything quoted in a pack carries its citation.** A pack is the coordinator's selection, not the coordinator's paraphrase: contracts are quoted, not described; decisions are ids with their recorded consequence; a summary line without a `[src:]` or an id does not go in. This is what keeps the helper building on evidence rather than on the coordinator's memory.

**Staleness stamp.** Each per-WP block records the commit (or the last passed gate) it was built from. The collect step compares it with the tree at collect time; if a file the block quoted changed in between, the block is marked `[STALE]` in the session log and the stage is re-launched with a fresh pack rather than trusting the result.

**Budget.** Target 10–20k tokens for a builder block, less for a reviewer block at Low; the script prints a token estimate and warns above 25k. When a WP genuinely needs more, prefer growing the on-demand read list over the quoted excerpts.

**Scoped reviewer block (attempt 2+).** `build_context_pack.py WP-NN --scoped` builds it from the previous review's findings, the diff since the previous gate (changed files and hunks only, computed from the gate's saved patch), the latest gate summary, the mutation-table rows added since, and the ACs — and prints `full_review_required` with the blast-radius triggers that fired, if any. The fix session gets the findings appended to the builder's conversation; it does not get a new pack unless it is a fresh fix helper.

**Exemptions.** Phase 5 (final audit) never uses a pack — reading everything is its job. Phase 0 has nothing to pack yet. A fix-loop session gets the reviewer's findings appended to the builder block, nothing else new.

## 3. What the user is told at question time

The option text carries the trade in one line each, so the choice is informed without reading this file:

- **None** — no independent review; gates are commands + self-check. ~0 extra cost. Gates no longer catch confident-but-wrong builds; every gate is marked, Phase 5 lists them. POC/spike only.
- **Low** — reviewer sees ACs, diff, gate output. ~5–10k tokens per review. Catches untested ACs and diff-level errors; misses anything outside the diff.
- **Medium (recommended)** — reviewer gets a context pack: ACs, quoted contracts, relevant ADRs, diff, hints, on-demand read list; shared block cached. ~15–30k per review. Catches most of what full reading catches; misses what the coordinator did not select — checked at the pilot.
- **High** — full reading: pack plus the whole playbook folder and repo. ~80–360k per review. Finds what nobody quoted; can cost more than the build it reviews.

After the pilot WP, the orchestrator reads back the pilot review's actual tokens and findings next to the chosen level, and offers to change it — that is the moment the estimate becomes a measurement.
