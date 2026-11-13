# Answer sources: openly licensed texts for technique and prevention

Ticket: `docs/work/answer-from-sources/issues/01-sources-and-licences.md`. Researched 2026-11-06. Not legal advice; the share-alike reading of embeddings is my analysis, marked as such.

## Answer

| Role | Source | Licence | Verdict |
|---|---|---|---|
| Core | English and Italian Wikipedia, a curated list of articles | CC BY-SA 4.0 | Use. Best coverage of technique, faults and risk, and the only source with Italian. |
| Support | free-exercise-db `instructions` | Unlicense | Use as step-by-step text. Thin on faults and prevention. Upstream text origin unverified. |
| Support | MedlinePlus health-topic summaries (NLM-written only) | US public domain | Use for general prevention. Almost no technique. |
| Support | HHS Physical Activity Guidelines, CDC pages | US public domain | Dose and safety only, if needed. |
| Rejected | OpenStax Anatomy & Physiology 2e | CC BY-NC-SA 4.0 | The commonly assumed CC BY is wrong: NonCommercial and ShareAlike. |
| Rejected | WHO guidelines | CC BY-NC-SA 3.0 IGO | NonCommercial. |
| Rejected | ExRx, NSCA/Human Kinetics, Mayo Clinic, A.D.A.M. | All rights reserved | See the last section. |

No open textbook on strength-training technique turned up. Technique questions rest on Wikipedia plus free-exercise-db.

## Share-alike and the repo

The repo is MIT (`LICENSE`, `pyproject.toml`).

| Question | Finding | Source |
|---|---|---|
| Does a collection of SA texts force SA on the whole repo? | No: "CC licenses do not require the collection or the compilation itself to be made available under an SA license"; each work keeps its own licence. | [CC FAQ](https://creativecommons.org/faq/) |
| What triggers SA? | Sharing "Adapted Material" you produce: material "translated, altered, arranged, transformed, or otherwise modified". Then the Adapter's License must be CC BY-SA with the same elements, or compatible, with no extra restrictions. | [CC BY-SA 4.0 legalcode](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en) 1.1 and 3(b) |
| Attribution duties | Creator, copyright notice, licence notice, disclaimer notice, URI to the material, an indication of changes, and the licence text or URI. | legalcode 3(a)(1) |
| Wikipedia attribution | A hyperlink to each page reused, or a link to a stable equivalent copy, or a list of authors. Name the licence and link it. Mark changes. | [Wikimedia Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) section 7; [Wikipedia:Copyrights](https://en.wikipedia.org/wiki/Wikipedia:Copyrights) |
| Text and data mining | The 4.0 licences "allow for text and data mining"; terms are not triggered by uses covered by an applicable legal exception. | CC FAQ |

My reading, for the spec to confirm:

- **Verbatim chunks** in the repo are copies, not adaptations. They keep CC BY-SA and need the attribution above. Put them under `corpus/` with their own `NOTICE`, so MIT covers the code and CC BY-SA covers the texts.
- **Translated, summarised or rewritten chunks** are adaptations and must be CC BY-SA. Avoid storing them; if a translation is needed, do it at query time.
- **Embeddings** are not settled by any CC text I found. Safest: do not commit vectors. Build them from the committed text with a script. If vectors are committed, treat them as part of the CC BY-SA corpus.
- **Answers shown to the owner** should carry the link and licence of the passage used, which the citation already does.
- **Reproducibility**: pin each Wikipedia page by revision id (`oldid`), recorded in a provenance table like the one beside free-exercise-db. This also freezes the eval.
- **Images**: take none. Wikipedia images each have their own licence, and non-free ones are excluded from CC BY-SA ([Wikipedia:Copyrights](https://en.wikipedia.org/wiki/Wikipedia:Copyrights)).

## Per source

### Wikipedia (English and Italian)

| | |
|---|---|
| Licence | CC BY-SA 4.0 ([Wikipedia:Copyrights](https://en.wikipedia.org/wiki/Wikipedia:Copyrights)); page footers say "additional terms may apply" |
| Coverage | English *Squat (exercise)*: sections Form, Variants, Clinical significance, Injury considerations. It covers depth, bracing, knee valgus and heel rise, torso flexion and disc risk, with citations, but few explicit cues. It carries an October 2025 banner saying some sources may be unreliable. English *Strength training* about 40k characters; *Deadlift*, *Bench press*, *Warming up*, *Delayed onset muscle soreness* each 3k to 17k. Thin: *Overhead press* 2k, *Lunge* 2k. |
| Italian | `it` *Squat* about 14k characters, *Panca piana* 14k, *Riscaldamento (sport)* 14k, *Lombalgia* 40k, *Allenamento con i pesi* about 70k. Some titles are missing (`Stacco_(esercizio)` returned a stub-sized result). Counts are JSON-escaped response sizes, so approximate. |
| Gaps | Few step-by-step cues; quality varies per page; some claims rest on weak sources (T Nation, lifting blogs) |
| Fetch | MediaWiki API `action=query&prop=extracts&explaintext=1&titles=...` or `action=parse&oldid=...`. Rate-limited: an unauthenticated burst got HTTP 429, so send a descriptive User-Agent and throttle. Full dumps exist at dumps.wikimedia.org. |
| Format | Plain text or wikitext, one article each; a curated list of 30 to 60 pages is under 2 MB |

### Wikibooks

*Physical Activity/Strength Training* (CC BY-SA, last edited 2018): five bullet exercises, no technique, no warm-up, a few lines on overload and rest. Not worth including. No Wikibooks book on lifting technique found.

### free-exercise-db `instructions`

| | |
|---|---|
| Licence | The Unlicense, public domain ([upstream](https://github.com/yuhonas/free-exercise-db), vendored in `src/trainer/data/free-exercise-db/LICENSE.md`) |
| Size | 876 records, `exercises.json` 1.0 MB, English only. Every record has an `instructions` list of short steps. About 51 lines match avoid/injur/warm. |
| Coverage | Setup and execution per exercise, with occasional "Tip:" lines. Almost no faults or prevention. Already in the repo, with a provenance file. |
| Caveat | The upstream README says the data was restructured from [wrkout/exercises.json](https://github.com/wrkout/exercises.json). I did not verify where that project's text came from, so the public-domain claim rests on the maintainers' word. |

### MedlinePlus

| | |
|---|---|
| Licence | Federal works are public domain. Credit "Source: MedlinePlus, National Library of Medicine". Copyrighted and excluded: A.D.A.M. Medical Encyclopedia, ASHP drug monographs, non-public-domain images, stock images ([terms](https://medlineplus.gov/about/using/usingcontent/)). |
| Coverage | *Exercise and Physical Fitness* is a short summary that links out to Mayo Clinic for technique and warm-up. It does not teach technique. Useful for general prevention and "see a doctor" statements. |
| Language | English and Spanish. The terms page mentions no Italian. |
| Fetch | Daily XML, e.g. `https://medlineplus.gov/xml/mplus_topics_2026-11-06.xml`, about 29 MB (4.7 MB zipped), with title, MeSH terms, full summary and links ([XML page](https://medlineplus.gov/xml.html)). Filter to the NLM-written summaries. |
| Duty | Indicate the source is MedlinePlus.gov. Do not alter URLs to appear under another domain. |

### US government guidance (HHS, CDC)

- **CDC**: most content is public domain. Duties: credit the agency, state that use does not imply endorsement, do not change substantive content, note the material is free at the agency site ([CDC](https://www.cdc.gov/other/agencymaterials.html)). Contractor and third-party items are excepted. The adult guidelines page gives the muscle-strengthening dose (2 or more days a week) but nothing on injury prevention or warm-up.
- **HHS Physical Activity Guidelines, 2nd edition**: PDFs (14.2 MB full, 2 MB summary). The page I fetched states no copyright terms and I did not confirm public-domain status, so check the PDF's own copyright page before use. It is dose guidance, not technique.
- Both are English only and answer "how much", which is the planner's domain, not the entrance's.

### Italian-language sources

- Italian Wikipedia is the only workable Italian corpus found.
- Ministero della Salute: I found no licence statement for its site or its 2021 physical-activity guidelines. Not usable until one is found.
- Other Italian public bodies (Protezione Civile, AIFA) use CC BY 4.0, but I found nothing on exercise from them.
- The alternative is English text with Italian questions: it needs a multilingual embedding model (to be measured in the retrieval ladder) and an Italian answer written at query time.

## Not allowed

| Source | Why |
|---|---|
| OpenStax *Anatomy & Physiology 2e* | CC BY-NC-SA 4.0, not CC BY. Shown by the [CMS API](https://openstax.org/apps/cms/api/v2/pages/?type=books.Book&slug=anatomy-and-physiology-2e&fields=license_name,license_url), the [collection file](https://raw.githubusercontent.com/openstax/osbooks-anatomy-physiology/main/collections/anatomy-and-physiology-2e.collection.xml) and the [repo README](https://github.com/openstax/osbooks-anatomy-physiology). NC conflicts with an MIT repo that anyone may use commercially, and SA would pull the corpus under NC-SA. It is anatomy, not technique, in any case. |
| WHO guidelines | CC BY-NC-SA 3.0 IGO; "Permission is required for commercial uses" ([WHO](https://www.who.int/about/policies/publishing/copyright)). |
| Kallipos *Strength Training* (Terzis, 2022) | CC BY-NC-SA 4.0 and Greek, per a search listing I did not open. |
| NSCA / Human Kinetics (*Essentials of Strength Training and Conditioning*, *Exercise Technique Manual*) | Commercial books. Search results show reproduction needs written permission from Human Kinetics (a single table was quoted at $90). The NSCA terms page returned 403 to my fetch, so this is not from a primary page. |
| ExRx.net | Its about page says it is ad-funded and grants permission case by case. I could not read its copyright page (403), so the exact terms are unconfirmed. Treat as all rights reserved. |
| Mayo Clinic, A.D.A.M., Healthline, T Nation and similar | Copyrighted. MedlinePlus links to Mayo for technique, but linking is not licensing. Mayo's terms page returned 403 to my fetch. |

Unchecked, possibly usable: the Pressbooks *Introduction to Biomechanics* (openedmb.ca), listed as CC BY 4.0 in a search result I did not open.

## Open questions for the spec

- Which Wikipedia pages go in the list, and whether pages with an unreliable-sources banner are acceptable.
- Whether to commit text under `corpus/` or fetch it at build time from pinned revisions.
- Cross-lingual retrieval versus Italian-only retrieval, to be measured.
- Whether the Pressbooks biomechanics text is worth a licence check.
