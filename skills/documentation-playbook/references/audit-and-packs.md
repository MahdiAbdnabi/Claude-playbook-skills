# Audit Effort, Context Packs, Self-Check & Step Budgets

What the execution playbook learned about cost and independence, applied to documentation. The failure modes are the same shape: phase agents re-read the whole corpus and playbook before extracting anything; an extractor's own confidence is not evidence; an audit that re-checks everything after every batch costs as much as the extraction. The guards are the documentation versions of the same rules.

## 1. Audit effort — asked before the run

Phase 5 is the only check that catches confident-but-wrong extraction, so its depth is a choice with a cost. Each option states what it costs and what it misses.

| Level | What the auditor receives | What it does | Typical input per audit | What you give up |
|---|---|---|---|---|
| **None** | — | No independent audit. `doc_check.py` runs (citations resolve, hedging, tag reconciliation) and that is all. The tracker marks the run `audit: none`; the usage guide says so on its first line. | 0 | The only defence against a citation that resolves to a real member but does not say what the document claims. For a 10-minute diagrams-only sketch, defensible; otherwise warned once. |
| **Low** | The `doc_check` report and a **mechanical citation sample**: N random `[src:]` rows with the cited member's text extracted by the script. | Reads each sampled member and confirms the claim; no falsification attempts; no reading beyond the sample. | ~5–10k | Everything outside the sample; consistency checks across documents. |
| **Medium** (recommended) | An **auditor pack**: shared block (cached), the sample with extracted member text, the documents in scope, the BRI/FLW/TST cross-reference table, the open GAP/DRIFT lists, and an on-demand read list into the code. | Confirms the sample, runs the consistency checks (every FLW decision → BR-###, every BR-### in TST, every `[PROTECTED]` has a status), attempts to **falsify five claims** of its own choosing from the documents in scope, and reports diagram elements as claims. | ~15–40k, shared block at cached price | Claims outside the documents in scope and the sample; the auditor is bounded by the pack's selection, so the pilot shape check asks whether it lacked anything. |
| **High** (full) | The pack plus the whole corpus and unrestricted code access. | Everything Medium does, plus free exploration: the convention nobody quoted, the module the batch plan missed, the rule in a file no citation reaches. | ~80–300k depending on corpus and repo | Cost; one audit can exceed a batch's extraction. |

Defaults: Low for 10-minute depth, Medium otherwise; High must be chosen. Record as `audit_depth`. The pilot's Phase 5 reads back the actual tokens and misses next to the chosen level and offers to change it for the remaining batches.

**Phase 5 stays fresh.** Whatever the level above None, the auditor is a new context that did not write the corpus. The extractor's self-check (§3) is not an audit; it removes the mechanical class of misses so the audit's effort goes to the semantic class.

## 2. Context packs

Phase agents are briefed with a pack, not a reading list. `scripts/build_context_pack.py` writes three files per launch under `docs/_playbook/packs/`:

```
packs/shared.md               immutable for the run; byte-identical every launch; FIRST in every helper prompt (cache prefix)
packs/<batch>-extractor.md    the extractor block for Phases 1–4 of one batch
packs/<batch>-auditor.md      the auditor block (Phase 5), built from the corpus and code — never from the extractor's block
```

**Shared block** (only what cannot change during the run): the seven principles, the tagging protocol, the 14-document taxonomy with the header convention, the active lenses, the resolved system name (or the naming GAP), the batch plan, the output profile, the repo map, the context rule (*do not read beyond your pack and its read list; if you need more, say what and why as a `[GAP]`*). Hashed; `--rotate-shared` is a logged decision because it invalidates the cache. Nothing dated goes in it.

**Extractor block**: the batch's modules with their paths, the documents this phase extends (and the exact sections it owns), the glossary terms earlier batches established (so names stay consistent), the open GAPs and DRIFTs that touch these modules, the seed `[PROTECTED]` invariants, the diagram level in force, the **files it may read on demand** (the batch's folders plus the shared ones Phase 0 named), and the **id ranges** it may allocate for GAP / DRIFT / BR / D-nodes so collects do not collide. Stamped with the corpus ref; a quoted file that changed before collect marks the result `[STALE]`.

**Auditor block**: by level per §1. Built from the finished documents, `doc_check.py`'s sample with extracted member text, and the logs; never from the extractor's working notes.

Phase 0 has nothing to pack yet and reads the repo directly; Phase 6 gets the shared block and IDX only.

## 3. Self-check — standard in every extraction phase

Before an extractor reports, it runs `python3 scripts/doc_check.py <docs-dir> --repo <repo> --batch <batch>` and resolves what it finds. The check is mechanical and cheap, so it is not a question; it is always on. It reports:

- **Citations**: every `[src: File#Member]` resolves to an existing file and the member name appears in it. Unresolved citations are listed; the extractor fixes the citation or turns the claim into `[GAP]`. External citations (`[src: SPEC §n]`, `[src: owner-answer GAP-###]`) are counted separately, not failed.
- **Untraced claims**: sentences in a document body with no tag at all are counted per document (an approximation — sentences with a tag anywhere count as traced); the maturity line must match the count within tolerance.
- **Hedging**: *probably, likely, presumably, appears to, should, typically, usually, I assume, seems* outside code blocks; each occurrence is either rewritten with evidence or converted to `[GAP]`.
- **Reconciliation**: `[GAP-###]` ids used in documents = rows in the GAP log; same for DRIFT; `[rule: TBD]` count (must be zero after Phase 3); every `[PROTECTED]` has a Phase 2 status line.
- **Headers**: every document and lens opens with the header convention and a maturity line.
- **Diagrams**: every node and edge in `diagrams/*.json` has `src` or a `gap`/`planned` tag.

The report is `logs/check-<n>.json` plus a short Markdown summary, stamped with the corpus tree hash. The phase's checkpoint includes the summary; a checkpoint with unresolved citations or hedges does not close.

## 4. Scoped re-audit and fixing by continuation

When Phase 5 misses the bar (hit rate < 90%, or any `[PROTECTED]` claim fails):

1. **Fix by continuing the extractor** of the affected batch — same conversation, the auditor's misses as facts ("a miss stands unless you show the cited member says what the document claims") — while that conversation is still cached and under the size threshold in `budget`; otherwise a fresh fix helper with the extractor pack plus the misses. The fix re-runs `doc_check.py` once. Recorded as `fix: continued / fresh`.
2. **Scoped re-audit** by a fresh auditor: the previous misses re-checked one by one, plus a fresh sample of five citations from the sections that changed (from the corpus diff since the previous check), plus the consistency checks on the changed documents only. One tier below the first audit's model unless a trigger escalates it: a miss was on a `[PROTECTED]` rule, more than a third of the batch's documents changed, or this is the third attempt. `build_context_pack.py --scoped` builds the block and prints `full_audit_required` with the triggers that fired.
3. Two fix loops, then the batch is `[BLOCKED]` with a Decision Card.

## 5. Step budgets

Each launch carries a tool-call cap from `budget_calls`, defaulted by depth (the number of documents a phase touches is what drives calls):

| Phase | 10min | 30min | full | Notes |
|---|---|---|---|---|
| 0 Recon | 12 | 16 | 20 | reads the repo; writes MOD draft and batch plan |
| 1 Core extraction | 15 | 25 | 40 | one batch; includes one `doc_check.py` call |
| 2 Rules & invariants | 12 | 18 | 25 | |
| 3 Closeout | — | 12 | 18 | skipped at 10min |
| 4 Lenses | 6 | 10 | 12 | reformatting only |
| 5 Audit | 8 | 12 | 20 | High audit effort: +10 |
| 5 re-audit | 5 | 8 | 10 | |
| 6 KB packaging | — | 8 | 10 | skipped at 10min |

Stopping at the cap with a clean handoff is a correct outcome: documents saved with their maturity lines updated, a "done / left / next" note in the tracker, no half-written sections. The orchestrator raises a Decision Card (continue +N · split the batch · stop); a cap hit twice on one batch recommends split. The cap never skips the self-check.

## 6. Decision Cards in a documentation run

The documentation playbook's checkpoints already stop with Blocking/High questions. A Decision Card (same format and script as the execution playbook: `scripts/build_decision_card.py`) is raised where a choice changes what the rest of the run produces:

| Trigger | Who decides |
|---|---|
| End of Phase 0: approve the batch plan and pilot (`DC-000`) | human in both modes unless the intake fixed them |
| After the pilot's Phase 5: the shape check — continue the pattern, adjust caps/lenses/diagram depth, or re-run the pilot | human / rule |
| A `[DRIFT]` touches a `[PROTECTED]` invariant | human in both modes |
| An audit miss on a `[PROTECTED]` claim; a batch `[BLOCKED]` after two fix loops | human in both modes |
| Reclassifying a document (an ARC that turned out to be inferred, not extracted) or dropping items for depth beyond the profile's caps | human / rule 4 |
| Call cap hit; switching audit effort, cost profile or output profile mid-run | human / rule |

Automated mode resolves the rule-eligible cards with the decision rules (the spec wins → never invent → drift logged both ways → simplest option meeting the profile → never weaken a check) and marks them `AUTO-DECIDED`; Phase 5 lists every auto-decided card for re-check.

## 7. Measurement

The tracker records per launch: phase, batch, model, calls against the cap, tokens, attempt, scope (full / scoped), fix (continued / fresh). At a glance it shows: citation hit rate per audit, **first-audit pass rate** across batches, unresolved citations and hedges at each checkpoint, calls and cap hits, audit tokens first → re-audit. These are the numbers the cost rules are judged by; a rule that does not move them is questioned rather than kept.
