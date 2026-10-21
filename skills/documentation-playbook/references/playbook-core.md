# Documentation Playbook — Core Methodology

Stack-agnostic version of the playbook. Bracketed slots (`[SYSTEM]`, `[BATCH]`, `[STACK]`, `[SEED INVARIANTS]`) are filled per run from Phase 0 output and the intake summary.

**Contents**
1. Non-negotiable principles
2. Document taxonomy (14 types)
3. Document header convention
4. Tagging protocol
5. Role lenses (summary — full catalog in `lenses.md`)
6. The seven phases, with prompts
7. Model & effort guide
8. Running in Cowork / Claude Code / a single chat
9. After the round: gap closure and delta rounds
10. Templates

---

## 1. Non-negotiable principles

1. **Cite or flag.** Every claim is `[src]`, `[PLANNED]`, `[GAP]`, or `[DRIFT]`. An answer invented to sound complete is worse than a gap, because a gap can be closed and a confident fabrication is only found by accident.
2. **Ground truth once, lenses after.** One core document per topic. Lenses point *into* the core; they never carry a claim the core lacks. Four (or more) independent copies will quietly disagree within a month.
3. **Protected invariants get the most scrutiny, not the least.** Anything tagged `[PROTECTED]` is actively re-verified every time a batch touches it. "Nothing flagged it" is not evidence of compliance.
4. **Documentation proves comprehension, not correctness.** "Behaves like X" is a weaker claim than "behaves like X and `[tested: …]` passes". Prefer the second where available; say plainly when it is not.
5. **Pilot one bounded context before batching the rest.** The most common failure of this pattern is committing full scope before the first pass has shown the output is useful.
6. **Ask early, not silently.** A blocking gap becomes a one-line question at the end of the phase that found it, not an entry in a log nobody reads until the end.
7. **Gaps are truth.** For code the documenter cannot fully reach, or a domain nobody on the team has worked in, the `[GAP]` count *is* the honest maturity measure. Lowering it by guessing is falsifying it.

---

## 2. Document taxonomy

One file per document type, extended batch by batch — never fragmented into per-batch files. That keeps retrieval (human or AI) pulling one right chunk instead of the whole corpus. File names: `NN_ID.md` in build order.

| # | ID | Document | Answers | Primary roles | Built in |
|---|---|---|---|---|---|
| 01 | **IDX** | Master Index & Glossary | Where do I go; what does this term mean? | All | Ph 3 draft → Ph 6 final |
| 02 | **ARC** | Architecture (logical / runtime / deployment; C4 context+container at minimum) | How is it structured and why? | Architect | Ph 1 |
| 03 | **DAT** | Domain & Data Model | Entities, storage shapes, keys, indexes, cache key-spaces? | Dev, Architect | Ph 1 |
| 04 | **MOD** | Module / Component Inventory | What units exist and how do they depend on each other? | Architect, Dev | Ph 0 draft → Ph 1 detail |
| 05 | **API** | Interface Surface | What contracts/endpoints/messages exist, with auth? | Dev, Architect | Ph 1 |
| 06 | **INT** | Integrations | What external systems, devices, queues does it talk to, and how? | Architect, Dev | Ph 1 |
| 07 | **XCC** | Cross-Cutting Concerns | Authn/authz, config, logging, errors, caching, i18n, concurrency, multi-instance? | Dev, QA | Ph 1 |
| 08 | **CNV** | Code Conventions as practised | What patterns are actually followed — inconsistencies included? | Dev | Ph 1 |
| 09 | **UXF** | UX & Interaction Flows | Screens/routes, navigation, state, what the user does? | BA, QA, Dev | Ph 1 |
| 10 | **FLW** | Key Business Flows | What happens end to end for each journey, and where is each step implemented? | BA, QA | Ph 1 pass 1 → Ph 3 pass 2 |
| 11 | **BRI** | Business Rules & Invariants | What logic governs behaviour; what must never change? | All | Ph 2 |
| 12 | **TST** | Test Coverage Map | Which BRI/FLW claims are backed by a real passing test? | QA, Dev | Ph 2 |
| 13 | **OPS** | Build / Deploy / Runbook | How is it built, configured, deployed, operated? | Architect, Dev | Ph 3 |
| 14 | **DEP** | Dependency Inventory | Packages, versions, support status, licence? | Architect, Dev | Ph 1 |

For a target without a UI (a workflow engine, a service), UXF documents the operator/consumer-facing surface (consoles, message contracts seen by callers) and says so in its header. For a target with no automated tests, TST still exists and is honest: it lists every rule as `[UNTESTED]`, which is the finding.

---

## 3. Document header convention

Every document opens identically — the maturity line is what makes partial completion visible instead of implied:

```
# [DOC-ID] — [Title]
System: [name resolved in Phase 0]
Scope: [batch name | "portfolio-wide" once consolidated]
Version: [DOC-ID] v[n], [date]
Authority: Ground-truth, traced to source. Verify against live code before relying on it for a change.
Maturity as of this pass: [X]% of scoped claims [src]-confirmed · [Y] [PLANNED] · [Z] [GAP] · [W] [STALE]
```

Lenses open with the same header plus `Lens: [ID] — read in ~10 minutes; points into the core, adds no claims.`

---

## 4. Tagging protocol

Eight tags do all the epistemic work. Used exactly like this, every phase, no exceptions — they are grep-queryable, which is the point.

| Tag | Means | Example |
|---|---|---|
| `[src: File.ext#Member]` | Directly confirmed at this location. Prefer `#Member` to `:line` (lines move). | `[src: MovementService.cs#CreateUpdateMovement]` |
| `[GAP-###: description]` | Could not be confirmed from what is reachable; nothing invented. Severity in the GAP log. | `[GAP-014] Risk-score expiry read from config, but no value found in any environment file.` |
| `[DRIFT-###: A vs B]` | Two sources disagree (legacy vs new, spec vs code, summary vs code). State both sides; do not pick. | `[DRIFT-003] Legacy BRI-007 required supervisor override; new controller accepts officer-level.` |
| `[PLANNED: description]` | Known and intentional — not built yet. Different question from `[GAP]`. | `[PLANNED] Re-verification within 24h is on the roadmap; no code exists.` |
| `[PROTECTED]` | Must-preserve invariant, seeded or designated in Phase 2 with the user's agreement. | Applied to seed invariants. |
| `[UNTESTED: BR-###]` / `[tested: TestClass.Method]` | Whether an automated test exercises the claim. | `[UNTESTED: BR-003]` — highest priority when also `[PROTECTED]`. |
| `[STALE]` | A `[src]` citation whose file changed since the citation was made (delta rounds). Cleared only by re-opening the file. | `[STALE] [src: RiskEngine.cs#Combine]` |
| `[rule: TBD]` | Placeholder on a FLW decision point until Phase 2 assigns a BR-### id. Must be zero by end of Phase 3. | — |

### 4.1 Ask during, ask after

Every phase ends with two artefacts: a **short direct question list** (only `Blocking` — next phase cannot proceed — and `High` — touches a `[PROTECTED]` rule), each phrased so it can be answered in one line; and the **running GAP log** with everything, including `Low`, so deferring an answer loses nothing.

---

## 5. Role lenses

Each lens is a ten-minute read that points into the core. Default four: **ARCH, DEV, QA, BA**. Optional and custom lenses, and the entry-points table, are in `lenses.md`. Lenses are assembled in Phase 4 from verified content only — if a lens needs something the core lacks, the core is incomplete; fix the core.

---

## 6. The seven phases

Pilot batch through Phases 1–5 first. Then remaining batches. Phase 5 again across everything. Phase 6 once.

The prompts below are the **full-depth, docs+diagrams** form. The run's output profile (`output-profiles.md`) adapts them: at 30-minute depth the Phase 1 output list collapses to the six digest files with per-section caps; at 10-minute depth Phase 1 extracts per lens into `EVIDENCE.md`, Phase 3 and 6 are skipped; in Docs-only mode every "diagram" line below becomes a table; in Diagrams-only mode the prose outputs are replaced by the diagram set and its evidence. Fill the `[PROFILE]` slot with the one-line profile statement so the phase agent knows which form to produce.

Diagram lines by phase (static → Mermaid in the document and in `diagrams/`; interactive → entries in `diagrams/<batch>.json`): Phase 1 draws D1–D3 (hld), D4, D5, D7 (design); Phase 3 finalises D6 flows and, at tracking depth, D8 traces; Phase 4 assembles D9 and D10 at tracking depth and writes lens diagram tours; Phase 5 samples diagram elements alongside prose citations.

### Phase 0 — Recon, naming, maturity map & pilot selection
**Model tier:** mid · effort high. **Output:** resolved system name (or naming GAP), MOD draft, maturity map, Batch Plan, pilot pick.

```
This is Phase 0 of the documentation playbook for the target reachable at [ACCESS].
Context from the owner (context, not evidence): [SUMMARY or "none provided"].

1. Establish the actual system name from solution/namespace/package/manifest structure.
   If more than one name appears across code, config and existing docs, log it as [GAP-001]
   rather than choosing.
2. Draft MOD: every deployable/unit/module/package ([STACK]-appropriate granularity), one line
   each on responsibility, plus the dependency graph between them.
3. Classify each module's maturity from the code: BUILT / PARTIAL / SCAFFOLD / NOT-STARTED.
   Tag not-yet-built as [PLANNED], not [GAP].
4. Propose a Batch Plan: 4–8 batches grouped by bounded context, mirroring real
   namespace/folder/reference structure — do not force a round number. For a very large
   target, batches may be nested (batch → sub-batches); say so.
5. Recommend ONE pilot batch: BUILT or mostly PARTIAL, touching at least one seed
   [PROTECTED] area if any were given, small enough to finish Phases 1–5 in one sitting each.
6. Inventory what is reachable vs not: test projects present? CI config? Infra-as-code?
   Databases reachable or inferred from code only? Each "not reachable" is a standing [GAP].

Output the above and stop. List Blocking/High gaps as one-line questions.
```

### Phase 1 — Per-batch core extraction *(repeat per batch, pilot first)*
**Model tier:** mid · effort high (small tier acceptable for DEP / DTO enumeration). **Output:** DAT, MOD detail, ARC, API, INT, DEP, XCC, CNV, UXF, FLW pass 1 for this batch.

```
This is Phase 1 for batch [BATCH] — modules: [MODULES]. Stack: [STACK].
Output profile: [PROFILE] — produce the form it asks for (full documents / digest / EVIDENCE.md;
diagrams static, interactive JSON, or tables).

Build this batch's slice of the ground-truth core, in this order (each supplies vocabulary
the next needs):
1. DAT — entities/documents/tables this batch owns: shapes, keys, indexes, embed-vs-reference,
   any cache key-space (pattern, TTL, what it coordinates).
2. MOD — this batch's modules in full detail beyond the Phase 0 one-liners.
3. ARC — how the pieces fit at runtime: call direction, in-process vs cross-process, threading
   or async model, any host↔embedded seam. C4 context + container level at minimum.
4. API / INT / DEP — the contract surface (cite the actual handler/DTO/schema, not an assumed
   convention); external systems, devices, queues; third-party packages and versions.
5. XCC — every auth enforcement point (each is candidate evidence for any authorization
   invariant), config sources, logging, error handling, caching, concurrency/multi-instance
   behaviour, i18n.
6. CNV — conventions as actually practised: naming, layering, DI, state management, async and
   error style. Where the batch is inconsistent with itself, document the inconsistency —
   do not pick a winner.
7. UXF — every route/screen/console this batch exposes: what it shows, what drives it, how it
   is reached, the user's sequence in plain language.
8. FLW pass 1 — business journeys through this batch: trigger → steps → decision points, each
   step already pointing at the implementing code. Mark each decision point [rule: TBD].
9. Diagrams (if the profile has them): D1 context, D2 container, D3 integration map from
   ARC/INT; at design depth or deeper also D4 components (MOD), D5 data model (DAT), D7 screen
   map (UXF). Every node and edge carries [src:] or a tag; draw [GAP] dashed, [PLANNED]
   hollow, [PROTECTED] outlined. Static: Mermaid in the document and diagrams/. Interactive:
   append to diagrams/[BATCH].json.

Tag every non-trivial claim [src: File#Member], [PLANNED] or [GAP]. Extend the existing
document files; update each header's maturity line. Then run
`python3 scripts/doc_check.py docs --repo <repo> --batch "[BATCH]"` and resolve every
unresolved citation and every hedging word (evidence or [GAP]) before reporting; include its
one-line summary in your checkpoint. Call budget: [CALL CAP] tool calls — stopping at the cap
with documents saved and a done/left/next note is a correct outcome. Stop after FLW pass 1 and
list Blocking/High gaps as one-line questions.
```

### Phase 2 — Business rules, protected invariants & test coverage
**Model tier:** strongest · effort xhigh. **Output:** BRI (incremental), TST.

```
This is Phase 2 for batch [BATCH]. Inputs: this batch's Phase 1 documents, and the seed
[PROTECTED] invariants: [SEED INVARIANTS or "none — propose candidates"].

1. For each seed invariant this batch could plausibly touch: find the implementation, cite it,
   and compare against the stated behaviour. Status: MATCH (cite both) / DRIFT (cite both,
   state the difference, do not judge which is right) / NOT-IN-THIS-BATCH.
2. Catalogue every other rule this batch enforces — validation, calculation, state transition,
   authorization — from XCC auth points, FLW decision points, and the actual conditionals.
   Assign BR-### ids. Each rule: plain-language statement, [src], inputs, outcome, and the
   FLW decision point(s) it resolves. Flag rules that look load-bearing enough to be
   [PROTECTED] and ask before applying the tag.
3. Build TST: for every BR-### in this batch, search the test code for a test that actually
   exercises it. Cite [tested: Class.Method] or tag [UNTESTED: BR-###]. Call out every
   [UNTESTED] + [PROTECTED] pairing as the single highest-priority item of this phase.
   If the target has no tests at all, TST says so once at the top and still lists every rule.

Run doc_check.py before reporting (every [PROTECTED] must carry a status line; no hedges).
Call budget: [CALL CAP]. Stop. List every [PROTECTED] status and every [UNTESTED][PROTECTED]
pairing as direct questions, even if nothing else needs input.
```

### Phase 3 — Flow finalisation, UX/Ops closeout & index draft
**Model tier:** mid · effort high. **Output:** FLW pass 2, remaining UXF, OPS, IDX draft.

```
This is Phase 3 for batch [BATCH]. BRI and TST exist for this batch.

1. FLW pass 2 — replace every [rule: TBD] with the real BR-### and every step with a stable
   [src]. Zero [rule: TBD] must remain for this batch.
2. Close UXF gaps Phase 1 left open now that BRI explains the "why" behind screen behaviour.
3. OPS — build, configuration, deployment, operation for what this batch touches. Tag what
   cannot be found [GAP]; never a guess at "how these things are usually done".
4. Extend IDX: this batch's terms into the glossary, its documents into the index. IDX is
   finalised in Phase 6, not here.
5. Diagrams (if the profile has them): finalise D6 per key flow with each decision point
   labelled by its BR-###; at tracking depth build D8 per flow — every step → [src:] member,
   every decision → BR-### → [tested:]/[UNTESTED], every external call → its D3 edge.
   Interactive: add the flow's ordered step list to diagrams/[BATCH].json so the page can
   step through it.

Run `doc_check.py … --phase 3` before reporting ([rule: TBD] must be zero). Call budget: [CALL CAP].
Stop. List remaining Blocking/High gaps as one-line questions.
```

### Phase 4 — Role lens assembly
**Model tier:** mid or small · effort medium (reformatting verified content; no discovery). **Output:** one `LENS-<ID>.md` per active lens for this batch.

```
This is Phase 4 for batch [BATCH]. Active lenses: [LENSES]. Output profile: [PROFILE].
Build each lens per lenses.md at the profile's depth — a ten-minute read (full), a ~30-minute
self-contained read (30min), or the single ten-minute page that IS the deliverable (10min) —
opening with "if you only read one thing", pointing into core sections by [DOC-ID §section]
(or EVIDENCE.md rows). In Diagrams-only mode the lens is a diagram tour: an ordered list of
diagrams to open with one line each on what to look for. At tracking depth assemble D9 (rules
↔ flows ↔ tests ↔ [PROTECTED]) and D10 (where each open GAP/DRIFT sits on D1–D8).
Introduce no new claims — if a lens needs something the core lacks, report it as a core gap
instead of adding it here. If length forced you to drop an item, say what and tag it
[PLANNED: full-depth run].
```

### Phase 5 — Evidence-based audit
**Model tier:** strongest · effort xhigh. **Output:** audit table + citation-sample hit rate. Run after the pilot, and again once all batches are through Phase 4.

```
This is Phase 5 over batches: [BATCHES]. Audit effort: [AUDIT LEVEL]. Your briefing is the
auditor pack (shared block first): the doc_check report, the citation sample with each cited
member's text, the documents in scope, and — at Medium/High — the cross-reference table, open
gaps and an on-demand read list (High: the whole corpus and repository). You did NOT write
this corpus; do not trust its maturity lines. First: confirm the doc_check tree hash matches
the current code. Call budget: [CALL CAP].

1. Build one table — columns: Rule/Invariant id | Stated/legacy behaviour [src or source] |
   Current behaviour [src] | Test evidence [tested:] or [UNTESTED] | Status
   (MATCH / DRIFT / UNVERIFIED / PLANNED). No prose "conforms" anywhere — a status without a
   citation is not evidence, and a holistic verdict hides exactly the rows needing a decision.
2. Citation-sample integrity check: the sample in your pack (15 citations; 20 if the corpus
   exceeds 500 claims; from `doc_check.py --sample`), each with the cited member's text —
   confirm it says what the document claims. Report hits/misses with the misses listed as
   M-## | doc | citation | claimed | code says, and write them to logs/audit-<n>-misses.json.
   This is the only check that catches confident-but-wrong extraction.
3. Consistency check: every FLW decision point resolves to a BR-###; every BR-### appears in
   TST; every [PROTECTED] has a status. List violations.

Stop and report. If the hit rate is below 90%, recommend which batch/phase to re-run before
scaling further.
```

### Phase 6 — AI knowledge-base packaging
**Model tier:** mid · effort high. **Output:** final IDX, Q&A-assistant system prompt.

```
This is Phase 6 — the corpus is complete for the planned scope. Do not create a second,
AI-only document set; two sources of truth drift. Instead:
1. Finalise IDX: per document a 2–3 sentence abstract, keyword tags, and an
   "ask about X → see [DOC-ID §section]" routing table; glossary consolidated.
2. Produce the Q&A-assistant system prompt (template §10.3) with this system's real document
   names and terms, and verify each example in it against the corpus.
```

---

## 7. Model & effort guide

Model tier sets *how capable*; effort sets *how thorough*. Raising effort within a tier is the cheaper lever — try it before moving up a tier. Tiers are `small` (Haiku) → `mid` (Sonnet) → `strong` (Opus) → `top` (Fable); efforts `low → medium → high → xhigh → max`. This table is the **Recommended** profile; the user's cost profile shifts it (`cost-and-orchestration.md §2`) and the tracker shows recommended, resolved and actually-used side by side.

| Phase | Nature of work | Tier | Effort | Critical |
|---|---|---|---|---|
| 0 Recon | structural discovery, moderate judgement | mid | high | — |
| 1 Core extraction | high-volume, mostly mechanical | mid; small for DEP/DTO enumeration sub-steps | high / medium | — |
| 2 BRI + invariants + TST | highest stakes, hardest to catch wrong later | **strong** | xhigh | **yes** |
| 3 Closeout | synthesis over gathered material | mid | high | — |
| 4 Lenses | reformatting verified content | small | medium | — |
| 5 Audit | the evidence the owner will act on; fresh context | **strong** | xhigh | **yes** |
| 5 scoped re-audit | previous misses + fresh sample from changed sections; fresh context | mid (one tier below the audit) | high | escalates to the audit tier on a trigger |
| 6 KB packaging | synthesis over a verified corpus | mid | high | — |

**Critical** phases floor at `mid`/`medium` under Very Low Budget and are the first to move to `top` under I Am Too Rich — they are where a wrong answer is both safety-relevant and hardest to catch afterwards. Mapping tiers to current model names is a run-time decision (names change); the orchestrator passes the resolved tier's name as the subagent's `model` and the resolved effort as its `effort` (`cost-and-orchestration.md §3`). In a single-model session the tier column collapses to effort guidance.

---

## 8. Running in Cowork / Claude Code / a single chat

- **Cowork / Claude Code:** one project pointed at the repo root; put §1–§5 in the project instructions (inherited once, not repeated per prompt); one phase (or one batch-phase) per session; save the corpus in `docs/` inside the repo so it versions with the code. Model and effort are picked per session, before launch.
- **Code reachable only through a Cowork project** (no local clone): the same, with the inventory of "not reachable" items from Phase 0 step 6 carried as standing gaps. Never infer from a description what the code would show.
- **Single chat (this skill, Fully Automated):** phases become subagent tasks; the tracker replaces the session boundary as the unit of progress. Each launch gets its context pack (shared block first), its call cap, and the self-check instruction; the session log records calls, tokens, attempt and scope per launch (`audit-and-packs.md`).

---

## 9. After the round

### 9.1 Pilot shape check (after the pilot's Phase 5)
Before scaling: lenses readable in ~10 minutes; zero `[rule: TBD]`; hit rate ≥ 90%; no `[PROTECTED]` silently `[UNTESTED]`; the owner found at least one lens useful. Fix the pattern, not the batches, if any fail.

### 9.2 Gap-closure pass (when the owner answers questions)
For each answered GAP: record the answer in the GAP log with `Answered by / on`, update the claim in the core document, and tag it `[src: owner-answer GAP-###]` — an owner's answer is a source, distinct from code. If the answer contradicts code, that is a new `[DRIFT]`, not a correction.

### 9.3 Failed audit: fix by continuation, scoped re-audit
Hit rate below 90%, or any `[PROTECTED]` miss: continue the batch's extractor conversation with the misses as facts (a miss stands unless the cited member is shown to say what the document claims) while that conversation is cached and under `budget_tokens_continue`; otherwise a fresh fix helper with the extractor pack plus the misses. `doc_check.py` runs once after the fix. A fresh auditor then does a **scoped re-audit** from `build_context_pack.py --scoped --misses logs/audit-<n>-misses.json`: each previous miss re-checked, five fresh citations from the changed sections, consistency checks on the changed documents only — one model tier below the first audit (`5re`) unless a trigger escalates it to a full audit at the first audit's tier: a miss on a `[PROTECTED]` rule, more than a third of the batch's documents changed, attempt 3. A miss "resolved" by deleting the claim without a `[GAP]` is a finding. Two fix loops, then the batch is `[BLOCKED]` with a Decision Card.

### 9.4 Delta round (when the code changes after the round)
Re-running everything is wasteful and loses the owner's answers. Instead:
1. Diff since the recorded corpus commit/date; list changed files.
2. Grep the corpus for `[src:` citations into changed files; tag each `[STALE]`.
3. Re-open each stale citation; clear `[STALE]` if still true, else update the claim (and log `[DRIFT]` if a `[PROTECTED]` rule moved).
4. New files/modules → run Phase 1 + 2 on them as a mini-batch.
5. Re-run Phase 5 step 2 (citation sample) over the touched documents; Phase 6 if IDX changed.
6. Update every touched header's maturity line and the tracker's delta log.

---

## 10. Templates

### 10.1 GAP log entry
```
[GAP-###] <one-line description>
Severity: Blocking | High | Low
Found in: [DOC-ID], Phase [n], batch [name]
Blocks: <what cannot proceed>
Question: <one line the owner can answer in one line>
Answered by / on: —
```

### 10.2 DRIFT log entry
```
[DRIFT-###] <one-line description>
Side A: <claim + source>
Side B: <claim + [src]>
Touches [PROTECTED]: yes | no
Decision needed from: <owner>
```

### 10.3 Q&A-assistant system prompt
```
You answer questions about [SYSTEM] using only its documentation corpus
(IDX, ARC, DAT, MOD, API, INT, XCC, CNV, UXF, FLW, BRI, TST, OPS, DEP and the lenses).
- Every answer cites [DOC-ID §section]. Never answer from how "systems like this" usually work.
- If the corpus does not cover it, say so and name it as a [GAP] rather than inferring.
- If the answer touches a [PROTECTED] or [UNTESTED] rule, say so and point to BRI/TST.
- If the corpus shows [DRIFT] on the topic, surface both sides.
- If a cited claim is [STALE], say the code may have changed since.
- Check IDX for the right document before searching broadly.
```
