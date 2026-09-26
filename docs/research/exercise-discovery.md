# Exercise discovery: widening the catalog from sources

Research date: 2026-09-26. A proposal, to be studied before it reaches ROADMAP.md.

## The idea

The catalog is 584 strength exercises and uneven: dumbbell 120, barbell 104, cable 81, body only 75, bands 17, medicine ball 2. Exercises that exist in the world and not in the catalog are **found, never invented**: searched online (e.g. ~200 cable exercises), their facts taken from a source, and the fields planning needs filled by a strong model where the rules cannot decide them.

## What it touches

| Rule | Where | How it holds |
|---|---|---|
| *Enumerate only what the world already enumerates* | TRAINER.md | a found exercise is one the world enumerates, with its source |
| *Nothing enters unless you can verify it was wrong* | TRAINER.md | fields measured against the reference set before any import |
| The agent never widens the admissible set | CONTEXT.md | only an accepted exercise enters it |
| Enrichment used no model and no network | TRAINER.md § Appendix | this adds both, measured |

## Decided so far

| | |
|---|---|
| Shape | an offline command first, like `trainer db import`, showing what would enter; in the chat later, reusing it |
| Sources | facts and the source URL are kept; instructions rewritten by the model citing the source; text and photos copied only from public-domain or free-licensed sources |
| Fields | the enrichment rules first; a field they cannot decide is filled by a strong model quoting the sentence it rests on |
| Safety | `loaded_joints` and `spinal_axial_load` carry exclusions: when unsure, more joints, never fewer |
| Measure | the model fills the fields of exercises the reference set already knows; 100% on the safety fields, a declared bar on the rest (ADR-0010); no pass, no import |
| Duplicates | a found exercise that is a variant of one already there becomes its `variant_of`, or is dropped; the count that matters is new exercises |

## Open

- Provenance: does an added exercise carry `catalog` / `added` (who, when, source), and is **Added exercise** a glossary term?
- Who accepts an import: the user row by row, or the measure alone?
- Which strong model, and what a full import costs.
- Where it goes: after 1.0.0, once exclusions are real (session 13).
