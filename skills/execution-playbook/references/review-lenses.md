# Review Lenses

A review lens is a perspective the adversarial reviewer must take, expressed as **concrete checks** it runs and reports under that lens. Lenses exist because "review this" produces a generic skim; "try to break this as a security reviewer, then as an operator" produces findings. Each finding in `review/WP-NN-review.md` is attributed to a lens, so the Decision Card can show *which perspective* objected.

## Default lenses (always on)

| ID | Perspective | Checks the reviewer runs |
|---|---|---|
| **CORRECTNESS** | Does it do what the acceptance criteria say — and nothing else? | Each AC-## has a test that asserts it and can fail; edge cases the AC implies (empty, boundary, concurrent, retry) are covered or `[PLANNED]`; error paths return the documented outcome; behaviour matches spec `[src:]`, and any mismatch is `[DRIFT]` not a silent fix; no scope creep beyond the WP. |
| **SECURITY** | Can it be misused, or does it trust what it should verify? | Every entry point authenticates and authorises server-side; inputs validated at the boundary; secrets not in code/config committed; dependencies added are known and pinned; injection/serialisation/path risks for the stack; logging does not leak sensitive data; irreversible actions guarded. |
| **MAINTAINABILITY** | Will the next person understand and safely change it? | Follows CLAUDE.md and existing conventions `[src:]`; no duplicated logic that already exists in the codebase; names say what things are; non-obvious choices have an ADR; tests are readable as specification; no hedging or TODO without a tag. |
| **OPERABILITY** | Can it be run, observed and recovered? | Configuration externalised and documented; failure modes logged with enough context; timeouts/retries/idempotency where calls leave the process; health/readiness where applicable; migration or data changes reversible or `[RISK]`-logged; gate commands reproducible from a clean checkout. |

## Optional lenses (offer in the pre-run question; default none)

| ID | Perspective | Checks |
|---|---|---|
| **PERFORMANCE** | Will it hold under the stated load? | Hot paths identified; N+1 / unbounded queries / unbounded collections; caching correctness (invalidation, TTL); any stated SLA has a measurement or is `[UNTESTED]`. |
| **UX** | Does a user get through it without guessing? | Flows match UXF/spec; error messages actionable; keyboard/accessibility basics; loading/empty/error states exist; RTL/i18n if in scope. |
| **DATA** | Is the data model sound and the data safe? | Schema/keys/indexes match DAT/spec; migrations idempotent and reversible; validation at write; PII handling; backup/restore path for changed stores. |
| **COMPLIANCE** | Does it respect the rules it must? | Protected invariants (`[PROTECTED]` from the docs) re-verified `[src:]` + `[tested:]`; audit trail for decisions the domain requires; retention and access rules. |
| **COST** | Is the spend proportionate? | New infrastructure/services justified in an ADR; token/compute budgets of the run respected; expensive calls bounded. |
| **DOMAIN** | Would a domain expert accept it? | Business rules BR-### from the corpus implemented as written; worst-case domain scenarios (the ones a BA would ask about) have tests; terminology matches the glossary. |
| **INTEGRATION** | Does it honour contracts on both sides? | Request/response shapes match the contract `[src:]`; versioning; failure behaviour of the other side handled; contract tests exist or `[UNTESTED]`. |
| **FIDELITY** | For content/extraction pipelines: is nothing lost or invented? | Every source item reachable in the output (coverage check); no placeholder or illustrative values; every content item carries `[src:]`; hashes match source. |

## Defining a custom lens

Add to the run config with the same shape; the reviewer prompt and the tracker pick it up:

```json
{ "id": "OFFLINE", "perspective": "Will it work with no network for the stated autonomy window?",
  "checks": ["every upstream call has a local fallback [src:]", "queue persistence survives restart (test)",
             "autonomy window from the spec is asserted by a test or [UNTESTED]"] }
```

Two sanity checks: a lens must have at least two checks the reviewer can actually run against code or tests (otherwise it is a value statement, not a lens), and it must not duplicate a default lens's checks (then extend the default's checks in the config instead).
