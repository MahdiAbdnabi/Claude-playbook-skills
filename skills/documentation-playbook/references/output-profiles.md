# Output Profiles

Four choices shape what the run produces. They never change the **rigor** — every claim still cites code or carries a tag, the GAP log is always complete, Phase 5 always samples citations — they change the **volume, the form, and which phases do how much work**. The tracker shows the four choices; the usage guide tells readers what they are holding.

| Choice | Options | Config key |
|---|---|---|
| **Depth** | `full` · `30min` · `10min` | `depth` |
| **Content mode** | `docs+diagrams` (default) · `docs` · `diagrams` | `content` |
| **Diagram style** | `static` (default) · `interactive` (HTML only) · `none` | `diagram_style` |
| **Diagram depth** | `hld` · `design` (default) · `tracking` | `diagram_depth` |

`diagram_style: none` is implied by `content: docs`. `content: diagrams` with `diagram_style: none` is a contradiction — ask again.

---

## 1. Depth

| Depth | What the reader gets | What the corpus is | How phases adapt |
|---|---|---|---|
| **full** | The 14-document corpus plus a ten-minute lens per role; the AI knowledge base. | All 14 documents, extended batch by batch. | Phases 0–6 exactly as `playbook-core.md §6`. |
| **30min** | One ~30-minute read per lens (≈ 4–6 k words or the diagram equivalent), self-contained, with an evidence appendix. | A **digest corpus** of 6 documents: `ARC`, `MOD+DAT` (merged as `STR` — structure), `FLW`, `BRI` (+ TST column), `UXF`, `IDX`. `INT`, `XCC`, `CNV`, `OPS`, `DEP` become sections inside `ARC`/`STR`, each capped at the top items by impact (what the most flows depend on). | Phase 1 extracts into the 6 digest files with per-section caps; Phase 2 unchanged (rules are never summarised — a rule either is or is not); Phase 3 closes FLW and IDX only; Phase 4 builds 30-minute lenses; Phase 5 samples 10 citations instead of 15; Phase 6 packages the digest. |
| **10min** | One ten-minute page per lens (≈ 1.5 k words or one diagram set), nothing else to read. | An **evidence appendix** (`EVIDENCE.md`): every claim any lens makes, with its `[src:]` and tags, grouped by lens. No standalone corpus documents. | Phase 1 is **lens-driven**: for each active lens, extract only what its entry points need, straight into EVIDENCE.md; Phase 2 runs on seed invariants and the rules the lens flows cross — not the whole rule catalogue (the uncatalogued remainder is one `[GAP]` saying so); Phase 3 is skipped; Phase 4 writes the lens pages; Phase 5 samples 10 citations from EVIDENCE.md; Phase 6 is skipped unless asked. |

Two rules hold at every depth. **Lenses add no claims**: in the 30-minute and 10-minute versions the lens *is* the main read, but every sentence still resolves to a row in the digest or in EVIDENCE.md. **Reduction is by selection, not by softening**: a shorter version drops items, it never hedges the ones it keeps. When an item is dropped for length, the lens says what was dropped and where the full extraction would put it (`[PLANNED: full-depth run]`), so the reader knows the edge of the map.

Time targets are reading time for the audience the lens names (a BA reads FLW faster than an architect reads XCC); after the pilot batch, ask one reader per lens how long it took and adjust the caps — that is part of the §9.1 shape check.

---

## 2. Content mode

| Mode | Produces | Does not produce |
|---|---|---|
| **docs+diagrams** | Documents (per depth) with diagrams embedded where the taxonomy calls for them (§4), plus a `diagrams/` set. | — |
| **docs** | Documents only. Where a diagram would normally sit, a table or list carries the same facts. | Any diagram. `diagram_style` and `diagram_depth` are ignored. |
| **diagrams** | The diagram set as the primary deliverable; each diagram carries its own evidence (node/edge → `[src:]`) and a short legend. Lenses become **diagram tours**: an ordered list of diagrams to open, with one line per diagram on what to look for. | Prose documents. The GAP/DRIFT logs and `EVIDENCE.md` still exist — they are what the diagram evidence panels read from. |

In `diagrams` mode the tagging protocol applies to diagram elements: a node or edge is `[src:]`-backed, `[GAP]` (drawn dashed, labelled), `[PLANNED]` (drawn hollow), `[DRIFT]` (drawn twice with both sides), `[PROTECTED]` (outlined). A diagram with an untagged element fails Phase 5 like a document with an untagged claim.

---

## 3. Diagram style

| Style | Form | Requires |
|---|---|---|
| **static** | Mermaid blocks in the Markdown; rendered to SVG in the HTML pages (`render_html.py` loads Mermaid). Printable; diffable; works in any Markdown viewer that renders Mermaid. | nothing |
| **interactive** | One HTML page per diagram set built by `scripts/build_diagram_page.py` from a diagram JSON (schema in the script): pan/zoom, click a node or edge → evidence panel with the claim, its `[src:]` and tags, level switch (HLD → design → tracking) on the same page, tag filter (hide `[PLANNED]`, highlight `[GAP]`/`[DRIFT]`/`[PROTECTED]`), lens toggle (dim what the current lens does not care about), and for flows a step-through that walks the path and opens each step's evidence. | **HTML**. If the format answer was MD, say in one line that interactive diagrams need HTML and ask whether to switch to Both; in Both, the Markdown carries the static Mermaid fallback and a link to the interactive page. |
| **none** | No diagrams; tables and lists instead. | — |

Interactive pages are self-contained files (Mermaid and the pan/zoom code inlined or loaded from a CDN — state which in the page footer; for offline hosting inline them). Nothing in an interactive page is a claim that is not also in the JSON, and nothing in the JSON is a claim that is not in the corpus/EVIDENCE — the page is a view.

---

## 4. Diagram depth

Diagram depth sets which diagram set exists. Each level **includes** the ones before it. The C4 vocabulary is used for structure; flows and rules get their own forms.

| Depth | Diagram set | Built in | Audience it serves first |
|---|---|---|---|
| **hld** — high-level design | `D1 Context` (system, actors, external systems, integration protocols on edges) · `D2 Container` (deployables, data stores, caches, message channels; every edge labelled with protocol and direction) · `D3 Integration map` (producer/consumer pairs, contract name on each edge) | Phase 1 (ARC/INT) | Architect, PO, BA |
| **design** | hld + `D4 Component` per container (modules and their dependencies, from MOD) · `D5 Data model` (entities, keys, embed/reference, from DAT) · `D6 Flow` per key business journey (activity or sequence form; decision points shown, each labelled with its BR-### once Phase 2 assigns it) · `D7 Screen map` (routes/screens and navigation, from UXF) | Phase 1 (D4, D5, D7), Phase 3 (D6 final) | Developer, QA, BA |
| **tracking** — full tracking | design + `D8 Trace` per flow: every step → the implementing member `[src:]`, every decision → BR-### → its test (`[tested:]`/`[UNTESTED]`), every external call → its D3 edge; `D9 Rule map` (rules ↔ flows ↔ tests ↔ `[PROTECTED]`) · `D10 Gap/drift overlay` (where in D1–D8 each open GAP and DRIFT sits) | Phase 3 (D8 after FLW pass 2), Phase 4 (D9, D10 assembled from BRI/TST/logs) | QA, Developer, Auditor, Rewrite team |

In `interactive` style the three levels are one page with a level switch; in `static` style they are separate Mermaid blocks under one heading. At `tracking` depth a static D8 can become unreadable for long flows — split by flow and by batch, and say so in the IDX.

Every diagram opens with the same header as a document (System / Scope / Version / Authority / Maturity), and the maturity line counts nodes and edges: `N nodes · E edges · x% [src] · g [GAP] · p [PLANNED]`.

---

## 5. How the four choices combine — worked examples

- **Full · docs+diagrams · static · design** (the default): the 14-document corpus, Mermaid diagrams D1–D7 embedded in ARC/MOD/DAT/FLW/UXF and collected in `diagrams/`, ten-minute lenses, KB packaging.
- **10min · diagrams · interactive · hld**: four (or more) diagram tours, one per lens, over a single interactive page holding D1–D3 with evidence panels; `EVIDENCE.md` and the GAP/DRIFT logs behind it; nothing else. Cheapest run that still has an audit.
- **30min · docs · none · (ignored)**: six digest documents, tables in place of diagrams, 30-minute lens reads. Good for a Markdown-only wiki.
- **Full · docs+diagrams · interactive · tracking**: the full corpus, plus one interactive page per batch holding D1–D10 with a flow step-through that opens each step's code citation — the heaviest profile; the orchestrator should budget Phase 3 and 4 at roughly double the default.

Record the four keys in `run-config.json`; the tracker prints them under run configuration and the usage guide opens with a sentence naming the version the reader is holding ("This is the 30-minute, diagrams-and-docs version at design depth; the full corpus was not generated").
