---
name: documentation-playbook
description: Run Mahdi's AI-assisted "documentation playbook" against a codebase or system — a phased, traceable extraction methodology (Phase 0 recon → core corpus → business rules & invariants → role lenses → evidence audit → AI knowledge base) with [src:]/[GAP:]/[DRIFT:]/[PLANNED]/[UNTESTED] tags, a 14-document taxonomy, and default Architect/Developer/QA/BA lenses. Use this skill whenever the user wants to document, reverse-engineer, extract architecture or business rules from, onboard people onto, or build an AI knowledge base for an existing system — legacy or new, any stack — and whenever they say "playbook", "document this codebase/system/repo", "extract the business rules", "ground-truth docs", "role lenses", "GAP log", or ask to re-run or update documentation after code changed. Trigger even if they only say "I want docs for this project that the architect, QA and BA can all use". Do NOT use for writing a single README, API reference, or a one-off explanation of a function.
---

# Documentation Playbook

Turns a codebase into **one shared ground-truth corpus** (14 document types, every claim traced to source or tagged as a gap) plus **thin role lenses** on top, with a **tracker** that shows exactly which phase, batch and gap is where. The playbook exists because AI-generated documentation reads fluently whether or not it is true — the tags and the audit phase are what make it auditable instead of merely plausible.

`references/playbook-core.md` is the methodology itself (principles, taxonomy, tagging protocol, phase prompts, model guide, delta rounds). `references/lenses.md` is the lens catalog. `references/cost-and-orchestration.md` defines the cost profiles and how the orchestrator launches phase agents with different models and efforts. `references/output-profiles.md` defines how depth (full / 30 min / 10 min), content mode, diagram style and diagram depth change what each phase produces. `references/audit-and-packs.md` defines audit effort, context packs, the mechanical self-check, scoped re-audits, call budgets and Decision Cards. Read all five before Phase 0 of any run. Everything below is about **how this skill runs the playbook**: intake, the two pre-run questions, the two execution modes, output formats, and the tracker.

## 1. Intake — two optional inputs

Both are optional. Ask for them once, together, in one short message; accept "skip" without pushing.

| Input | Why it helps | If absent |
|---|---|---|
| **Project summary** — business (what it does, for whom) and technical (stack, deployment shape) if the user knows it | Seeds Phase 0 with vocabulary and the real system name; lets Phase 2 know which rules are load-bearing | Phase 0 derives everything from the code and logs naming as `[GAP]` if ambiguous. Never substitute assumptions for a missing summary. |
| **How to reach the documentation target** — connected folder, repo path, attached archive, a URL, a connector (GitHub, Drive), or "it's in this Cowork project" | Decides whether Claude can read the code itself or must work from whatever is attached | Look first: connected folders, attachments, repos in this session. If nothing is reachable, ask for access once; if still nothing, stop — the playbook cannot run on a description of code. |

If the conversation already contains a summary or the target (an attached repo, a folder the user connected earlier, an earlier turn describing the system), take it from there and confirm in one line instead of asking again.

A summary the user gives is **context, not evidence**. Claims in the corpus still cite code. Where the summary and the code disagree, that is a `[DRIFT]`, logged, not silently resolved either way.

## 2. Pre-run questions — ask before anything is generated

Ask with `AskUserQuestion` when it is available, in **three rounds**: round one is *how the run executes* (Q1–Q4), round two is *what the output looks like* (Q5–Q8), round three is *how hard the audit works* (Q9). In plain text otherwise. Do not start Phase 0, do not generate the tracker, until all are answered — the answers change what gets built, what form it takes, and what it costs.

**Q1 — Execution mode**
- **Fully Automated** — the whole playbook runs without the user. Claude executes every phase and batch itself, keeps the tracker current, logs every gap, and surfaces the question list at the end. It stops only for decisions that cannot be undone and could reasonably go either way (e.g. overwriting an existing `/docs` corpus).
- **User Monitored** — the user manages prompt execution. Claude prepares each phase prompt (filled in for the current batch), runs it only on the user's go, stops at every phase checkpoint with the Blocking/High questions, and waits. The user may also copy the prompt into their own Cowork/Claude Code session and report back; the tracker then records what they ran.

**Q2 — Output format**: **HTML**, **MD**, or **Both**. Markdown is always the authoring format (it is what the AI knowledge base and `[src]` grep work on); HTML is rendered from it with `scripts/render_html.py`. "HTML only" still writes Markdown to a `_src/` folder so later rounds and delta rounds have something to diff — tell the user this in one line.

**Q3 — Execution cost profile** (details and the exact resolution rules in `references/cost-and-orchestration.md`):
- **Very Low Budget** — Haiku does most of the work; every phase drops two model tiers and one effort step, except the critical phases (business rules & invariants, evidence audit), which floor at Sonnet so the audit is still a real check.
- **Recommended** (default) — the playbook's own per-phase guide: the most efficient model for each phase at the most efficient effort. Cheap phases stay cheap; the two high-stakes phases do not.
- **I Am Too Rich** — always one cost level above recommended: one model tier up for every phase, and one effort step up where a phase is already on the top tier.

Record the profile in the config (`cost_profile`), regenerate the tracker, and read back the resolved model/effort table to the user in one line before Phase 0 (e.g. "Recommended: Sonnet/high for 0,1,3,6 · Opus/xhigh for 2,5 · Haiku/medium for 4"). Switching profile mid-run is allowed; it applies to phases not yet started and is logged as a decision.

**Q4 (optional) — Additional lenses**: the four defaults (Architect, Developer, QA, BA) always apply. Offer the optional catalog from `references/lenses.md` as a multi-select, defaulting to none. A lens the user names that is not in the catalog is fine — define it in the tracker's config block using the same entry-points / primary-concerns shape.

### Round two — output profile (rules in `references/output-profiles.md`)

**Q5 — Depth**
- **Full documentation** — the 14-document corpus, a ten-minute lens per role, the AI knowledge base. Phases 0–6 as written.
- **30-minute version** — one ~30-minute self-contained read per lens over a six-document digest (`ARC`, `STR`, `FLW`, `BRI`, `UXF`, `IDX`); the smaller documents fold into those as capped sections.
- **10-minute version** — one ten-minute page per lens and nothing else to read; behind it an `EVIDENCE.md` holding every claim with its `[src:]`. Phase 1 becomes lens-driven extraction; Phases 3 and 6 are skipped.

**Q6 — Content mode**: **Docs + diagrams** (default) · **Docs only** (tables and lists where diagrams would sit) · **Diagrams only** (the diagram set is the deliverable; lenses become diagram tours; prose documents are not written, but `EVIDENCE.md` and the GAP/DRIFT logs still are).

**Q7 — Diagram style** (skip if Docs only): **Static** (Mermaid in Markdown, SVG in HTML) · **Interactive** — HTML only: pan/zoom, click any node or edge for its evidence and tags, level switch, tag filter, lens toggle, flow step-through. If the format answer was MD, say so in one line and ask whether to switch to Both; the Markdown then carries static fallbacks.

**Q8 — Diagram depth** (skip if Docs only): **High-level design** (D1 context · D2 container · D3 integration map) · **Design** (default; adds D4 components · D5 data model · D6 flows · D7 screen map) · **Full tracking** (adds D8 per-flow trace step→code→rule→test · D9 rule map · D10 gap/drift overlay). Each level includes the ones before it.

Record `depth`, `content`, `diagram_style`, `diagram_depth` in the config. Whatever the profile, the rigor does not change: every claim and every diagram element is `[src:]`-backed or tagged, the GAP log is complete, and Phase 5 samples citations. A shorter version **drops** items and says what it dropped (`[PLANNED: full-depth run]`); it never softens the ones it keeps. Read the chosen profile back to the user in one line, with any phase skips it implies, before Phase 0.

### Round three — checking (rules, cost figures and mechanisms in `references/audit-and-packs.md`)

**Q9 — Audit effort**: how the Phase 5 auditor is briefed and how far it looks. State cost and effect with each option:
- **None** — no independent audit; only the mechanical `doc_check` (citations resolve, no hedging, tags reconcile). ~0 extra. Nothing catches a citation that resolves but does not say what the document claims; the run is marked `audit: none`. 10-minute sketches only; warned once otherwise.
- **Low** — a fresh auditor confirms a random citation sample with the cited members' text extracted by the script. ~5–10k per audit. Nothing outside the sample.
- **Medium** (recommended; default for 30-minute and full) — an auditor pack: the sample, the documents in scope, the BRI/FLW/TST cross-reference, open gaps, an on-demand read list; the auditor runs the consistency checks and tries to falsify five claims of its own choosing. ~15–40k per audit, shared block cached.
- **High** — the pack plus the whole corpus and repository. ~80–300k. Finds the module the batch plan missed; can cost more than the batch it audits.

Default Low at 10-minute depth, Medium otherwise; High is chosen, never assumed. Record as `audit_depth`. After the pilot's Phase 5, read back its actual tokens and misses next to the chosen level and offer to change it. The extractor's self-check is not a question — it always runs (§4) — and it never lowers audit effort: it removes the mechanical class of misses so the audit's effort goes to the semantic class.

Also settle silently, from context, before generating anything: the **output location** (`docs/` inside the target if writable, else a `docs-<system>/` folder in the workspace, delivered as files), and whether a **previous corpus** exists there (if yes, this is a delta round — see `playbook-core.md §9` — not a fresh run; confirm with the user, since reruns overwrite).

## 3. Generate the tracker and the usage guide first

Before Phase 0, produce two things in the chosen format(s) and show them to the user:

1. **Execution tracker** — `scripts/build_tracker.py` from a config JSON (schema in the script header). It writes `TRACKER.md` and/or `TRACKER.html`. The tracker holds: run config (mode, format, cost profile, lenses, and per phase the recommended / resolved / actually-used model and effort), the phase × batch matrix with status, the GAP log, DRIFT log, decision log, citation-sample results, session log, and **a "next action" line** that names the exact next prompt. The tracker is the single place a returning user (or a fresh session) looks to know where the run is — in Fully Automated mode Claude updates it after every phase; in User Monitored mode Claude updates it after every checkpoint and the user can tick items in the HTML version.
2. **Short usage guide** — `USAGE.md` / `USAGE.html`, generated by the same script. One screen: what the corpus is, how to read a tag, where to start per role, how to answer a GAP, how to run a delta round, how to switch mode. Keep it to what a teammate needs on day one; the full methodology stays in the playbook, not the guide.

Phase 0's batch plan is not known yet when the tracker is first built — generate with `batches: []`, then regenerate (same config, batches filled) after Phase 0 and keep regenerating as status changes. The script is idempotent: config is the source of truth, trackers are views of it. Keep the config at `docs/_playbook/run-config.json`.

## 4. Running the phases

Follow `references/playbook-core.md §6` for the seven phases and their prompts; the prompts there are stack-agnostic, so fill the bracketed slots (system name, batch, modules, stack specifics, seed invariants) from Phase 0 output and the intake summary. Rules that hold in both modes:

- **Pilot first.** Phase 0 picks one pilot batch; run it through Phases 1–5 before any second batch. After the pilot's Phase 5, do a shape check: are the lenses actually a ten-minute read, do the FLW decision points resolve to BR-### ids, is the citation-sample hit rate acceptable? If not, fix the pattern before scaling — that is cheaper than fixing eight batches.
- **The orchestrator launches, it does not extract.** The agent running this skill is the orchestrator: it resolves the per-phase model/effort table for the chosen cost profile, then delegates each phase (per batch) to a subagent via the `Agent` tool with `model` and `effort` set from that table — so one run can have Haiku enumerating dependencies, Sonnet extracting the core, and Opus or Fable verifying invariants, each phase on the model the playbook recommends for it. Give the subagent the playbook-core principles, the filled phase prompt, the tracker's current state, and the output paths; launch independent batches at the same phase concurrently; take back GAP/DRIFT entries into the tracker; log every launch (phase, batch, model, effort, outcome) so the tracker's "actually used" column is true. The Phase 5 auditor is always a fresh agent that did not write the corpus. If `Agent` is unavailable, run phases in sequence yourself, lean on effort, and mark audits `self-review` in the tracker. Full rules: `references/cost-and-orchestration.md §3`.
- **Helpers get a pack, not a reading list.** Before launching a phase for a batch, run `scripts/build_context_pack.py "<batch>" --phase N` to produce `packs/shared.md` (immutable for the run, hashed, placed **first** in every helper prompt so prompt caching reuses it) and the batch's extractor block (modules, the sections this phase owns, the glossary earlier batches established, open gaps and drift, seed invariants, the on-demand read list, the GAP/DRIFT/BR id ranges it may allocate). Phase 5 gets an auditor block built from the corpus and `doc_check` — never from the extractor's block. A quoted file that changed before collect marks the result `[STALE]`. A helper that needs something outside its pack raises a `[GAP]`; it does not roam. Rules: `audit-and-packs.md §2`.
- **Every extraction phase ends with the self-check.** The extractor runs `scripts/doc_check.py docs --repo <repo> --batch "<batch>"` before reporting: every `[src: File#Member]` must resolve, hedging words are rewritten with evidence or converted to `[GAP]`, GAP/DRIFT ids reconcile with the logs, `[rule: TBD]` is zero after Phase 3, every `[PROTECTED]` has a status, every diagram element is tagged. A checkpoint with unresolved citations or hedges does not close. The report is stamped with the code's tree hash; the auditor's first action is to confirm it still matches.
- **Steps are budgeted.** Every launch carries the phase's tool-call cap from `budget_calls` (defaulted by depth; `audit-and-packs.md §5`), enforced with `max-turns` where the tool offers it. Stopping at the cap with a clean handoff — documents saved with maturity lines updated, a done/left/next note in the tracker — is a correct outcome; the orchestrator raises a Decision Card (continue +N · split the batch · stop). The cap never skips the self-check.
- **Decision Cards at the real decision points.** DC-000 approves the batch plan; a card closes the pilot shape check; a `[DRIFT]` on a `[PROTECTED]` invariant, an audit miss on a protected claim, a reclassified document, a batch `[BLOCKED]` after two fix loops, and any mid-run change of profile all raise one (`audit-and-packs.md §6`, same `scripts/build_decision_card.py` and format as the execution playbook). Ordinary Blocking/High gap questions stay as checkpoint questions — a card is for a choice that changes what the rest of the run produces.
- **A failed audit is fixed by continuing the extractor, and re-audited only where it changed.** Hit rate below 90% or any `[PROTECTED]` miss → the batch's extractor conversation is continued with the misses as facts (while cached and under the size threshold; otherwise a fresh fix helper with the pack + misses), `doc_check` runs once, and a fresh auditor does a **scoped re-audit**: the previous misses one by one plus five fresh citations from the changed sections, one model tier below the first audit unless a miss was on a `[PROTECTED]` rule, more than a third of the batch's documents changed, or it is the third attempt (`build_context_pack.py --scoped` prints `full_audit_required` with the triggers). Two fix loops, then `[BLOCKED]` and a card.
- **Gaps are truth.** Nothing is invented to fill a gap, in either mode. Fully Automated mode does not "guess so the run can continue" — it logs `[GAP]`, continues on what is known, and carries the question forward. A rule whose implementation cannot be found is `[GAP]`; a rule that is found but has no test is `[UNTESTED]`; something not built yet is `[PLANNED]`. These are different claims and collapsing them is the most common way a run degrades.
- **Every non-trivial claim carries `[src: File.ext#Member]`.** An untraced claim is treated as unverified at Phase 5. Prefer file#member over file:line — lines move.
- **Checkpoints.** Every phase ends with (a) the Blocking/High gaps as one-line questions and (b) the full GAP log updated. In User Monitored mode, stop there and wait. In Fully Automated mode, record them in the tracker, update "next action", and proceed; present the consolidated question list when the run ends or when a `[PROTECTED]` rule turns out `[UNTESTED]` or `[DRIFT]` — that pairing is worth interrupting for even in automated mode, because it is the one finding the user most needs to see early.
- **Write documents incrementally, in the shape the profile asks for.** Full depth: one file per document type (`01_IDX.md … 14_DEP.md`). 30-minute: the six digest files. 10-minute: `EVIDENCE.md` only. All extended batch by batch, headers per the convention, maturity line updated each pass. Lenses in `lenses/LENS-<ID>.md` (diagram tours in Diagrams-only mode). Render HTML after each phase if HTML was chosen, so the user can always open a current page.
- **Diagrams are claims too.** When diagrams are on, each phase emits the diagram set its depth calls for (`output-profiles.md §4`): static Mermaid blocks go into the documents and `diagrams/`; interactive sets are a `diagrams/<batch>.json` per batch (schema in `scripts/build_diagram_page.py`) rendered to an HTML page after each phase. Every node and edge is `[src:]`-backed or tagged — dashed for `[GAP]`, hollow for `[PLANNED]`, outlined for `[PROTECTED]`, doubled for `[DRIFT]` — and the Phase 5 citation sample draws from diagram elements as well as prose.
- **Audit is a table, not a verdict.** Phase 5 produces the evidence table and the citation-sample hit rate. No prose "conforms".

## 5. Finishing a run

Deliver, in this order: the one-line result (batches done, documents produced, hit rate, open Blocking/High count), the tracker (file card or link), the usage guide, then the question list as a numbered list of one-liners the user can answer in place. Do not recap the phases. If the output lives in a connected folder, say where; otherwise send the files (zip the corpus if more than ~10 files).

Offer one next step only: answering the questions (which triggers a gap-closure pass — `playbook-core.md §9.2`), or scheduling a delta round when the code next changes.

## 6. Resuming or updating an existing run

If the user comes back ("continue the playbook", "where were we", "the code changed, update the docs"), read `docs/_playbook/run-config.json` and the tracker first, then:
- an unfinished run → resume at the tracker's "next action" in the recorded mode (ask only if they want to switch mode);
- answered GAPs → gap-closure pass;
- changed code → delta round (`playbook-core.md §9`), which re-verifies affected `[src]` citations and marks them `[STALE]` until re-confirmed, rather than re-running everything.

## Files in this skill

- `references/playbook-core.md` — the methodology: principles, 14-doc taxonomy, header convention, tags, phases with prompts, model/effort guide, Cowork notes, delta rounds. Read at the start of every run.
- `references/lenses.md` — default lenses and the optional catalog, with the shape to define a custom one.
- `references/cost-and-orchestration.md` — the model/effort ladders, the three cost profiles and their resolution rules, and how the orchestrator launches phase agents with different models and efforts.
- `scripts/build_tracker.py` — config JSON → `TRACKER.md` / `TRACKER.html` + `USAGE.md` / `USAGE.html`. Run `python3 scripts/build_tracker.py --help`.
- `references/output-profiles.md` — depth, content mode, diagram style and diagram depth: what each produces, how the phases adapt, the D1–D10 diagram taxonomy, and worked combinations.
- `references/audit-and-packs.md` — audit effort levels with cost and effect, context packs, the mechanical self-check, scoped re-audit and fix-by-continuation, per-phase call budgets, Decision Card triggers, measurement.
- `scripts/doc_check.py` — the mechanical check: citations resolve to file#member, hedging words, GAP/DRIFT reconciliation, `[rule: TBD]`, `[PROTECTED]` statuses, headers, diagram tags; `--sample N` extracts cited members for the auditor. Stamped with the code's tree hash.
- `scripts/build_context_pack.py` — `packs/shared.md` (hashed cache prefix), per-batch extractor block, auditor block sized by audit effort, `--scoped` re-audit block with escalation triggers.
- `scripts/build_decision_card.py` — Decision Card JSON → MD/HTML + register in the config (shared with the execution playbook).
- `scripts/render_html.py` — renders the Markdown corpus (and lenses) into self-contained HTML pages with a sidebar index, tag highlighting, and Mermaid rendering for static diagrams. Needs `pip install markdown` (the script says so if missing).
- `scripts/build_diagram_page.py` — diagram JSON → one interactive HTML page: pan/zoom, click-to-evidence, level switch, tag filter, lens toggle, flow step-through. `--help` for the schema.
- `assets/run-config.example.json` — a filled example config to copy from.
- `assets/decision-card.example.json` — a filled pilot shape-check card.
- `assets/diagram.example.json` — a small diagram set (D1–D8 nodes, edges, evidence, flows) to copy the shape from.
