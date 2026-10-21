# Decision Cards

A Decision Card is a one-screen record raised at a phase boundary: what was done, what the evidence says, what the options are, what is recommended, and what happens if nobody answers. It exists so decisions are made **with the gate's evidence in front of the decider**, and so an unattended run leaves a trail a person can audit afterwards instead of a pile of silent choices.

## When a card is mandatory

| Trigger | Card id pattern | Who decides |
|---|---|---|
| End of Phase 0 (approve the work-package breakdown) | `DC-000` | Human in both modes. Rule-resolution is allowed only if locked decisions already cover every option. |
| Design → Build of each WP | `DC-<n>` | Human (monitored) / rules (automated) |
| Verify PASS → next WP | `DC-<n>` | Human / rules |
| Verify `[BLOCKED]` (two failed fix loops) | `DC-<n>` | **Human in both modes** — the run stops |
| An ADR with more than one viable option appears mid-stage | `DC-<n>` referencing `ADR-###` | Human / rule 4 (simplest) — Phase 5 re-checks every rule-4 use |
| An irreversible action is about to happen (destructive migration, delete, publish, external side effect) | `DC-<n>` | **Human in both modes** (rule 7) |
| Options differ in cost beyond the run's stated budget | `DC-<n>` | **Human in both modes** (rule 8) |
| A `[DRIFT]` touches a `[PROTECTED]` rule or a definition-of-done item | `DC-<n>` | Human in both modes |
| Design's test plan exceeds the derived test budget (`self-check.md §4`) | `DC-<n>` (options: approve / trim / split the WP) | Human / rule 4 picks "trim to budget" unless Logic effort is I Am Too Rich |
| Lowering the self-check level mid-run | `DC-<n>` | Human in both modes |
| A stage hits its tool-call cap (`step-budgets.md §3`) | `DC-<n>` (options: continue +N / split the WP / stop) | Human / rule 4: continue +50% once, then split; a second cap hit on the same WP recommends split |

Cards are numbered sequentially across the run; the WP they belong to is a field, not part of the id.

## Format

```
# DC-### — <title: the decision in one line>
Between: Phase <x> → Phase <y>   WP: WP-NN   Raised: <date>   Status: OPEN | DECIDED | AUTO-DECIDED | SUPERSEDED
Stops the run: yes | no          Reversible: yes | no         Budget impact: none | <estimate>

## What was done
<2–4 lines, with [src:] to the WP file / review / gate log>

## Evidence
- Gate commands: PASS/FAIL (attempt n) — <one-line summary> [src: logs/…]
- Reviewer verdict: PASS/FAIL — findings: F-01 (High, SECURITY) …, F-03 (Low, MAINTAINABILITY) …
- Open gaps raised here: GAP-###, GAP-###
- ADRs needing a call: ADR-###

## Question
<one line, answerable in one line>

## Options
| | Option | Consequence | Cost | Reversible | Risk |
|---|---|---|---|---|---|
| A | <recommended first> | … | … | yes/no | … |
| B | … | … | … | … | … |
| C | … | … | … | … | … |

## Recommendation
<option letter> — <one reason, tied to the evidence>

## Default if unanswered (automated mode)
<option letter> by decision rule <n> — or "none: waits for a human" when the trigger is human-only

## Decision
<option letter> · by <person | AUTO rule n> · on <date> · rationale: <one line>
Follow-ups: ADR-### accepted/superseded · GAP-### answered · tasks added to WP-..
```

## How automated mode resolves a card

1. If any human-only trigger applies (BLOCKED, irreversible, over budget, protected drift, DC-000 without full locked decisions) → status stays `OPEN`, the run stops at this card, the tracker's next action names it.
2. Else apply the decision rules in order (`playbook-core.md §7`): spec wins → never invent → drift logged → simplest option satisfying the ACs → never weaken a gate → no new dependencies. The first rule that determines an option decides; the card records `AUTO-DECIDED · rule n`.
3. If no rule determines an option (the options are genuinely equivalent under the rules), pick the recommendation and record `AUTO-DECIDED · recommendation` — Phase 5 lists these for human re-check.

## How a person answers a card

One line is enough: `DC-007: B — keep CoreWCF out, hand-roll the dispatcher; revisit if contract set grows`. The skill applies it, updates `DECISIONS.md`, marks follow-ups, regenerates the tracker, and continues from the card's "next" phase. Answering several cards at once is fine; they are applied in id order.

## Generating a card

`scripts/build_decision_card.py card.json` writes `decisions/DC-###.md` (and `.html` when the format includes HTML) and appends the card's summary row to `run-config.json`'s `decision_cards` register so the tracker shows it. The JSON schema is in the script header; `assets/decision-card.example.json` is a filled example.
