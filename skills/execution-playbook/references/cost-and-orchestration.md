# Cost Profiles & Orchestration

The playbook recommends a model tier and an effort level per phase. The **cost profile** the user picks before the run shifts those recommendations up or down; the **orchestrator** (the agent running this skill) then launches each phase's subagent with the resolved model and effort, and records what was actually used.

## 1. The ladders

| Model tier | Maps to (Agent tool `model`) | Typical use in the playbook |
|---|---|---|
| **small** | `haiku` | enumeration, reformatting verified content, bookkeeping |
| **mid** | `sonnet` | discovery, extraction, synthesis, builds |
| **strong** | `opus` | business rules / invariants, adversarial review, audit |
| **top** | `fable` | the same phases when a wrong answer is safety-relevant and hardest to catch later |

Effort ladder: `low → medium → high → xhigh → max`.

Model tier → name is a run-time mapping; if a name is unavailable in the session, step down one tier and record it in the session log — never silently skip the phase or merge it with another.

## 2. The three profiles

Ask as a pre-run question (one of the three; default **Recommended** when the user is absent).

| Profile | Rule | What it means in practice |
|---|---|---|
| **Very Low Budget** | model = recommended **−2** tiers (floor `small`); effort = recommended **−1** step (floor `low`). Phases flagged **critical** floor at `mid` / `medium` instead. | Haiku does most of the work. Critical phases (the ones whose errors are hardest to catch later) still get Sonnet so the gate is not theatre. The tracker shows the profile so nobody mistakes a budget run for a recommended one. |
| **Recommended** | model and effort exactly as the playbook's per-phase guide. | The most efficient model for each phase at the most efficient effort — already tuned so the cheap phases are cheap and the two or three high-stakes phases are not. |
| **I Am Too Rich** | model = recommended **+1** tier (cap `top`); when already at `top`, effort **+1** step (cap `max`). | Always one cost level above recommended. Reviews and audits run on Fable; extraction on Opus; enumeration on Sonnet. |

A phase is **critical** when the playbook's model guide marks it so (the rules / invariants phase, the adversarial review, the final audit). The flag lives in the config's `models` block (`"critical": true`) and the resolver honours it; a user can clear it, and that is itself a recorded decision.

Resolution is mechanical and lives in `scripts/build_tracker.py` (`resolve_models`). The tracker prints three columns per phase: recommended, resolved for this profile, and actually used (from the session log) — so a cost overrun or a quiet downgrade is visible, not inferred.

## 3. Orchestration

The orchestrator is the agent in whose context the skill was invoked. It does not do the phase work itself when subagents are available; it **plans, launches, collects, records, decides**:

1. **Plan** — read run-config, resolve the model/effort table for the chosen profile, write it into the config and regenerate the tracker before launching anything.
2. **Launch** — for each phase (per batch / work package), call the `Agent` tool with `model` set to the resolved tier's name and `effort` set to the resolved effort, passing: the playbook principles, the filled phase prompt, the current tracker state, the output paths, and — for reviewers and auditors — *nothing* of the producer's reasoning (a fresh agent, never a continuation). Independent units (two batches at the same phase, several reviewers) launch in the same turn so they run concurrently.
3. **Collect** — take the subagent's GAP/DRIFT/decision entries into the config; take its outputs into the corpus or repo; never re-interpret its findings as the orchestrator's own.
4. **Record** — one session-log row per launch: phase, batch/WP, model, effort, tokens if the tool reports them, outcome. This row is what makes the "actually used" column truthful.
5. **Decide** — apply the mode (automated: continue by rule; monitored: stop at the checkpoint / Decision Card), set `next_action`, regenerate the tracker.

**Degrading gracefully.** If `Agent` is unavailable the orchestrator runs the phases itself in sequence; the profile then collapses to effort guidance, and reviews/audits are done as a separate pass after discarding working notes — the tracker marks these `self-review` so the weaker guarantee is visible. If a requested model is unavailable, step down one tier and log it.

**Cost guard.** When the session log shows a phase consuming more than twice its budget (tokens or turns, whichever the run states), the orchestrator stops and raises a Decision Card (execution playbook) or a checkpoint question (documentation playbook) offering: continue, switch profile for the remaining phases, or pause — regardless of mode. Switching profile mid-run is allowed and is recorded as a decision; the resolver recomputes only the phases not yet started.
