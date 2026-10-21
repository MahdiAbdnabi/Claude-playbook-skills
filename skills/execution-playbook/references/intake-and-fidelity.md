# Intake, Fidelity, Effort Allocation & Tooling

These settle *what* is being built and *how good* it has to be before any work-package exists. They are recorded in `run-config.json` and printed at the top of the tracker; Phase 0 consumes them when it frames the task.

## 1. Task summary — mandatory, from one or more sources

A run does not start without a summary. It can come from any combination of:

| Source | How it is taken | Record as |
|---|---|---|
| **User description** — what they typed or said | Used as given; unstated constraints become `[GAP]`s, never defaults. | `summary_sources: ["user"]` |
| **A document** — attached spec, issue, RFP, design doc, linked page, a file in the connected folder | Read it; summarise it in ≤ 10 lines with `[src: DOC §n]` on each line; disagreements between documents become `[DRIFT]`. | `["document: <name>"]` |
| **Suggested from the expected output** — when the user gives only the result they want ("a dashboard that shows X") | Draft the summary backwards from the output: what it must do, for whom, with what inputs, under what constraints you can infer and which you cannot (`[GAP]`); read it back and get a one-line confirmation. | `["suggested"]` |

The summary has two halves, both required (either may be "none known", but that is a stated fact, not a missing one): **business** (what, for whom, why now, what done looks like to them) and **technical** (stack, constraints, locked decisions, non-goals, integrations). A confirmed suggested summary is as binding as a typed one; it is still intent, not evidence, and still yields `[DRIFT]` when the target disagrees with it.

## 2. Expected output — identified before execution

Before anything else is asked, the expected output is written down as **observable artefacts**, each with where it will live and how its existence is checked:

```
expected_output:
  - artefact: "Scenario picker in the simulation panel"   where: "modern-entryexit-core / sim-panel"   check: "Playwright test opens the panel and lists ≥1 scenario from the API"
  - artefact: "ADR for library caching"                   where: "_playbook/adr/"                       check: "file exists, status Accepted"
```

An expected output that cannot be checked is a `[GAP]` and blocks Phase 0 — a run that cannot tell whether it has finished cannot be gated. The expected output becomes the top of the definition of done in `PLAYBOOK.md`; Phase 5 traces every item of it to an acceptance criterion and a passing test.

## 3. Technology suggestion (coding tasks)

If the task is coding and neither the summary nor the expected output names the technologies, Claude proposes them before Phase 0 and the user's answer becomes locked decisions. The proposal is one recommended set plus one or two alternatives, each a short line: language/runtime, framework, storage, test tooling, build/run — and *why it fits this task at this fidelity*. Rules of thumb:

- **What is already in the target wins.** An existing repo's stack is the default; proposing a different one is an ADR-level change and goes on the card as an alternative, not as the recommendation.
- **Size the stack to the fidelity.** A Fastest POC gets the fewest moving parts that can show the logic working (single process, in-memory or file storage, no auth, no build pipeline beyond `run`); an MVP gets the real storage and the real integration seams; Full gets the production stack.
- **Honour stated constraints**: offline hosting, licensing, team familiarity, corporate standards, the locked stack of a parent programme.
- **Never pick silently.** The proposal is asked with `AskUserQuestion` (recommended option first); absent an answer in unattended mode, the recommendation is taken under decision rule 4 and logged `[DC-### AUTO rule 4]`.

## 4. Fidelity level — asked before execution

| Level | Goal | What it changes |
|---|---|---|
| **Fastest POC** | Make the happy path work, as cheaply as possible, to prove the logic. Not a product; labelled as such in every artefact header. | Technology: least cost that can run the logic (§3). Architecture: the simplest design that works — one project, flat structure, no layering unless the logic demands it. Validations: only what the happy path needs to execute; input validation, error paths, auth, concurrency are `[PLANNED]`, listed once in `PLAYBOOK.md`. WPs: 1–3. Tests: one smoke test per WP proving the happy scenario; it still runs before the code is written. Gates: gate commands + reviewer on **CORRECTNESS (happy path) only**; other lenses off, said so in the tracker. Phase 5: definition-of-done trace only; no citation sample. ADRs: one, recording that this is a POC and what it skipped. |
| **MVP** | Complete a working part of the solution — a vertical slice that a user can exercise end to end — while keeping an architecture that can grow. | Technology: the real stack for the slice. Architecture: good design and solution structure, following the target's conventions, with ADRs for non-obvious choices; parts outside the slice are `[PLANNED]` with their intended place. Validations: the main ones — input validation at the boundary, the authorization gates, the error paths users hit, the invariants the slice touches. WPs: as Phase 0 proposes, scoped to the slice. Tests: acceptance tests for every AC. Gates: full, default lenses. Phase 5: full. |
| **Full implementation** | Ready and tested, considering the best approaches. | Everything in MVP plus: non-functional ACs (performance, operability, security) written and tested or `[UNTESTED]` with a reason; all lenses the user selected plus OPERABILITY and SECURITY checks at full depth; handover complete (runbook, deploy, delta-round notes); Phase 5 includes the citation sample and the rule-4 re-check. |

The level is a scope decision, not a rigor decision: at every level the tests come first, the reviewer is a fresh context, gaps are tagged, and a gate is never weakened. What changes is how much is in scope and which lenses the reviewer applies. Moving up a level later is a delta round (`playbook-core.md §9.3`) that re-opens the `[PLANNED]` items — which is why a POC must list them.

## 5. Effort allocation — three dimensions

Asked as three questions, each **Very Low · Recommended · I Am Too Rich**. The cost profile (`cost-and-orchestration.md`) decides *which model* runs a stage; effort allocation decides *how much work that model is asked to do* in each area. Default is Recommended on all three; a fidelity of Fastest POC defaults all three to Very Low unless the user says otherwise.

| Dimension | Very Low | Recommended | I Am Too Rich |
|---|---|---|---|
| **Logic** | Implement exactly the stated rules and ACs; edge cases beyond them are `[PLANNED]`. | ACs plus the edge cases they imply (empty, boundary, retry, concurrent), error paths, and the invariants the WP touches, each with a test. | Exhaustive: property-based or table-driven tests for every rule, invariant verification across instances, adversarial inputs, a DOMAIN-lens pass even if not selected. |
| **Architecture & solution design** | Simplest structure that works; no ADRs beyond the locked decisions; follow whatever the target already does. | Layered to the target's conventions; ADR for every non-obvious choice with options and consequences; contracts and data shapes designed before code. | Full design pass per WP: C4 context/container/component for what it touches, options analysis on every ADR, NFR review (scale, failure modes, security), extensibility and migration path considered and recorded. |
| **UI design** | Functional and unstyled: default components, no layout work; states beyond success are text. | Consistent and usable: follows the target's design system or a plain one, accessible basics (keyboard, contrast, labels), loading/empty/error states, responsive to the stated devices. | Polished: a design pass using the `frontend-design` skill before Build, deliberate typography and spacing, micro-interactions where they aid use, RTL/i18n if in scope, UX-lens review. |

Two interaction rules. A dimension set to **I Am Too Rich** under a **Very Low Budget** cost profile runs that dimension's stages at the Recommended model tier (Design for architecture, Build for logic and UI) — asking Haiku for a full design pass wastes the effort. A dimension set to **Very Low** does not lower the gate: the ACs that *are* in scope still get real tests and a real review. UI design is skipped (recorded as "n/a") when the task has no user interface.

## 6. Tooling — Claude only, or other tools and integrations

Ask whether Claude alone executes the task, or other tools and integrations are expected. If others:

1. **Name the mapping**: for each tool, skill, MCP server or connector — what it is used for, in which WPs, and what it produces. The user may name some; Claude proposes the rest from what the expected output needs (an image-generation MCP for game art, a design tool for mockups, a database connector for seed data, a CI system for the gate commands, a ticketing connector for the task list).
2. **Check availability** in the session (connectors, MCP tools, skills, installed CLIs). Each entry gets `available` / `needs-setup` (how) / `missing`.
3. **Record** it in `run-config.json` → `tooling`, and in `PLAYBOOK.md`. Each WP Design names the tool for every output it produces that way, and its gate checks the produced artefact like any other (an asset file exists, loads, matches its spec `[src:]`).
4. **At Build time a missing tool is a `[GAP]` and a Decision Card** — never a silent substitution with something Claude can do by hand. The card's options are: set it up, substitute (named), or defer the output `[PLANNED]`.

Example entry:
```
tooling:
  - tool: "PixelLab MCP"      used_for: "2D sprites, tilesets and animations for the officer-desk scene"   wps: ["WP-04","WP-07"]   availability: "available"   produces: "assets/sprites/*.png with a manifest"
  - tool: "frontend-design skill"   used_for: "UI design pass before WP-07 Build (UI effort: I Am Too Rich)"   wps: ["WP-07"]   availability: "available"
  - tool: "GitHub Actions"    used_for: "gate commands in CI after each passed WP"   wps: ["all"]   availability: "needs-setup: workflow file in WP-00"
```

"Claude only" is also recorded, so a later session does not reach for a tool the user excluded.
