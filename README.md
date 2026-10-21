# Claude skills — execution-playbook

A gated execution playbook for Claude: any multi-step build task is cut into work packages, each designed, built tests-first, verified by gate commands and a fresh adversarial reviewer, and closed with a Decision Card.

## Install

**Claude.ai / Claude desktop** — upload `execution-playbook.skill` under Settings → Capabilities → Skills → Upload skill. (Team/Enterprise owners can provision it organisation-wide from Admin settings.)

**Claude Code, per repository** — copy `skills/execution-playbook/` into your repo as `.claude/skills/execution-playbook/` and commit; everyone who clones the repo gets it.

**Claude Code, personal** — copy it to `~/.claude/skills/execution-playbook/`.

## How a run flows

Open [`docs/execution-flow.html`](docs/execution-flow.html) for the interactive page (level of detail, guards table, model per stage, PNG export). The two diagrams:

**One run, end to end** — intake and the three question rounds, Phase 0 and DC-000, the work-package loop with its fix / scoped re-review branch and BLOCKED exit, then the final audit and handover.

![Execution flow overview](docs/execution-flow-overview-light.png)

**Inside one work package** — Build (context pack → tests first → implement → mutation harness → one gate run) and Verify (tree-hash check → fresh adversarial review), with the fix loop that continues the builder and re-reviews only what changed. Dashed boxes are scripts that ship with the skill.

![Work-package loop](docs/work-package-loop-light.png)

Dark-theme versions: [`execution-flow-overview-dark.png`](docs/execution-flow-overview-dark.png), [`work-package-loop-dark.png`](docs/work-package-loop-dark.png).

## What is in the skill

| Path | Purpose |
|---|---|
| `SKILL.md` | How the skill runs: intake, pre-run questions (fidelity, effort, mode, format, cost profile, tooling, reviewer effort, self-check), the per-WP loop, finishing and resuming |
| `references/playbook-core.md` | Principles, tags, phases with prompts, gates, decision rules, model guide, templates |
| `references/intake-and-fidelity.md` | Mandatory summary, expected output, technology suggestion, fidelity levels, effort dimensions, tooling plan |
| `references/cost-and-orchestration.md` | Model/effort ladders, cost profiles, the orchestrator loop |
| `references/review-depth.md` | Reviewer effort levels and context packs |
| `references/self-check.md` | Build self-check: mutation sweep, control tests, derived test budget |
| `references/step-budgets.md` | Per-stage call caps, harness, structured gate summaries, one gate run per stage, measured baseline |
| `references/review-lenses.md`, `references/decision-cards.md` | Reviewer lens catalog; Decision Card format and triggers |
| `scripts/build_tracker.py` | run-config → tracker + usage guide (MD/HTML) |
| `scripts/build_decision_card.py` | Decision Card JSON → MD/HTML + register |
| `scripts/build_context_pack.py` | Shared / builder / reviewer packs; `--scoped` re-review packs with blast-radius triggers |
| `scripts/gate.py` | Runs gate commands once; structured summary stamped with the tree hash; `--verify`, `--show` |
| `scripts/mutate.py` | Mutation harness: worktree per mutant, baseline guard, sentinels |
| `scripts/render_html.py` | Markdown → HTML pages |
| `assets/` | Example run config and decision card |

Scripts need Python 3.10+ and git; `render_html.py` needs `pip install markdown`.

## Trying it

Point Claude at a repository and say "run the execution playbook on this". The skill asks its questions, generates `_playbook/TRACKER.md` and `_playbook/USAGE.md`, and starts Phase 0.
