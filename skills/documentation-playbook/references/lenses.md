# Role Lenses

A lens is a ten-minute read for one audience that points into the shared core by `[DOC-ID §section]`. It never carries a claim the core lacks. Each lens opens with an **"If you only read one thing"** pointer, then **Entry points** (which core documents, in which order), then **What to watch for** (the `[PROTECTED]`, `[UNTESTED]`, `[DRIFT]` and open `[GAP]` items that matter to this audience), then **How to ask** (how this audience phrases a question to the Q&A assistant, with two examples from this system).

## Default lenses (always on)

| ID | Audience | Entry points (in order) | Primary concerns |
|---|---|---|---|
| **ARCH** | Architect | ARC, MOD, INT, DEP, XCC | boundaries, seams, topology, contract surfaces, dependency risk, what would break under change |
| **DEV** | Developer (incl. new joiners) | MOD, CNV, DAT, API, UXF, BRI (code-linked), TST | "where do I look to change X", conventions as practised, the `[src]`-cited rule list, what is covered by tests before touching anything `[PROTECTED]` |
| **QA** | Tester | FLW, BRI (as test oracle), TST, UXF, GAP log | decision points and expected outcomes, tested vs untested, edge cases already flagged |
| **BA** | Business analyst / product | FLW (plain language), BRI (business terms, minimal code), UXF (screens in business terms), IDX glossary | what the system does for the business, in language a non-technical stakeholder can follow |

## Optional lenses (offer in the pre-run question; default none)

| ID | Audience | Entry points | Primary concerns |
|---|---|---|---|
| **OPS** | Operations / SRE / support engineer | OPS, XCC (logging, config), INT, DEP | how it is deployed and configured, what to look at when it breaks, external dependencies that can fail, runbook gaps |
| **SEC** | Security reviewer | XCC (authn/authz, every enforcement point), API, INT, BRI (authorization rules), DEP | trust boundaries, auth gates and their tests, secrets/config handling, vulnerable or unsupported dependencies |
| **DATA** | DBA / data engineer / reporting | DAT, INT (data feeds), BRI (calculation rules), OPS (migrations, backups) | schemas and keys, data lifecycle, what calculates what, migration and retention |
| **PO** | Product owner / sponsor | FLW (one page), BRI (`[PROTECTED]` only), maturity lines, GAP log (Blocking/High) | what exists vs `[PLANNED]`, which rules are load-bearing, what decisions are waiting on them |
| **SUP** | Helpdesk / L1 support / trainers | UXF, FLW (user-facing steps), IDX glossary | what the user sees, in what order, and what each message or state means |
| **INTG** | Integration partner / consuming team | API, INT, XCC (auth), DAT (shared shapes) | contracts as implemented (not as advertised), auth required, versioning, failure behaviour |
| **MIG** | Rewrite / migration team | BRI (all, with `[PROTECTED]`), FLW, DAT, TST, DRIFT log | everything that must survive the rewrite, where parity is unproven, where the two systems already disagree |
| **AUD** | Compliance / external auditor | BRI, TST, Phase 5 audit table, GAP/DRIFT logs | evidence trail: rule → implementation → test → status, with nothing asserted without a citation |

## Defining a custom lens

When the user names an audience not in the catalog, add it to the run config with the same shape; the tracker and Phase 4 pick it up:

```json
{ "id": "TRN", "audience": "Classroom trainers", "entry_points": ["UXF", "FLW", "IDX"],
  "concerns": "the sequence a trainee must learn, and which screens are safe to demo" }
```

Two sanity checks before accepting a custom lens: it must map to at least two core documents (otherwise it is a section of a document, not a lens), and it must not need a claim the core does not hold (otherwise the taxonomy needs a document, not the lens list).
