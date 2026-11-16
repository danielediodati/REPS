# More corpus sources: what else may be added, and what it would fix

Research date: 2026-11-13. A proposal, to be studied before it reaches ROADMAP.md. Follows [More open sources](../work/answer-from-sources/issues/11-more-open-sources.md), which is not repeated here except where it left a verdict unverified.

Bar for "open": public domain / US government work, CC0, CC BY, CC BY-SA, redistributable verbatim in a public MIT repo with no condition on its users. Out: NonCommercial, NoDerivatives, "free to read", custom clauses. Every licence below was read on the publisher's own page unless the row says otherwise. Several publisher sites refused automated fetches (Cloudflare, CloudFront, Gcore, HTTP 405); those are in section 4, never guessed, and I did not try to get round the blocks.

## 1. The gaps, and where the repo shows them

Corpus version 1: 3868 chunks. By source and language (counted from `src/trainer/data/corpus/chunks.jsonl`):

| Source | Lang | Chunks |
|---|---|---|
| Wikipedia | en | 1791 |
| Wikipedia | it | 1685 |
| US Army ATP 7-22.02 | en | 222 |
| wger | it | 126 |
| MedlinePlus | en | 44 |

| # | Gap | Evidence in the repo |
|---|---|---|
| G1 | Technique cues and common faults are thin and rest on a few passages per lift | `docs/work/answer-from-sources/issues/11-more-open-sources.md` ("Technique is thin"); the Army text is 222 chunks across 11 chapters; the latest answer-suite snapshot `tests/eval_suites/answer.txt` shows the row `depth` answered *not covered* and `heels` citing a passage the row does not label |
| G2 | Italian technique text is almost only Wikipedia (about 25 exercise pages) and wger one-line descriptions (126 chunks) | `chunks.jsonl` counts above; `docs/answering/eval-set.toml` has about 80% Italian rows, and spec story 27 holds half of the Italian covered rows to an English-only passage |
| G3 | Named accessory exercises have no source at all | `near` rows in `eval-set.toml`: `pallof`, `dead-bug-progression`, `turkish-get-up-steps`, `hip-airplane`, `jefferson-curl`, `tibialis-raise`, `monster-walk`, `skater-squat`. Wikipedia has no page for Dead bug, Turkish get-up, Face pull, Hip airplane or Jefferson curl (checked 2026-11-13 against the `en.wikipedia.org` API); it.wikipedia has none for Stacco rumeno, Face pull, Squat frontale |
| G4 | Recovery and modalities beyond foam rolling | `near` rows `massage-gun`, `ice-bath-minutes`, `running-shoes-mileage`, `knee-wraps-tension` |
| G5 | Evidence with numbers (volume, frequency, rest, proximity to failure, injury-prevention dose) | covered rows `rest-for-strength`, `always-to-failure`, `how-to-progress`, `strength-days-per-week`, `reps-per-movement` lean on Wikipedia prose and four MedlinePlus pages; the MedlinePlus topics in the manifest yield only 44 chunks |
| G6 | Programme brands | `near` rows `wendler-531`, `gzcl-tiers`: books under copyright; stays *not covered* by design, no open source exists |
| G7 | Nutrition | out of scope by the map ("technique and general prevention"); one row (`creatine-dose`) exists and is the only pressure |

## 2. Recommended sources

All below are English. For Italian (G2) nothing new could be verified (section 4).

| Source | Publisher | Licence, page read, quoted wording | Duties | Provenance check | Gap | Size and format | How to pin |
|---|---|---|---|---|---|---|---|
| **CC BY open-access reviews and trials on strength training**, picked by hand (examples below) | Springer (Sports Medicine, Sports Medicine - Open), Frontiers, PLOS ONE, BMC, BMJ (BJSM, BMJ Open SEM), MDPI | Per article. Springer, <https://link.springer.com/article/10.1007/s40279-022-01804-x>: "This article is licensed under a Creative Commons Attribution 4.0 International License, which permits use, sharing, adaptation, distribution and reproduction in any medium". Frontiers, <https://www.frontiersin.org/articles/10.3389/fphys.2019.00376/full>: "distributed under the terms of the Creative Commons Attribution License (CC BY)". PLOS, <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0229507>: "Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction in any medium". BMJ via PMC, <https://pmc.ncbi.nlm.nih.gov/articles/PMC10579176/>: "Re-use permitted under CC BY". MDPI via PMC, <https://pmc.ncbi.nlm.nih.gov/articles/PMC8296276/>: "Creative Commons Attribution (CC BY) license" | CC BY: credit authors, title, journal, DOI, licence link, say if changed. Springer: "images or other third party material ... are included in the article's Creative Commons licence, unless indicated otherwise in a credit line", so keep prose only, drop figures and tables, and drop any passage reproduced from another source | Original research or review by the authors; no derivative of a restricted work seen. The licence is the article's own, so check each one, never the journal: BMC Medicine is CC BY 2.0 (<https://bmcmedicine.biomedcentral.com/articles/10.1186/1741-7015-10-75>) | G5, G1/G6 in part: dose-response, injury prevention, foam rolling, cold water, EMG of lifts, Nordic, tendinopathy | 30 to 40 articles, 5 to 15 pages each, JATS XML or HTML | DOI + PMCID + Europe PMC licence field recorded at fetch time; text SHA-256 per article. Retrieve through Europe PMC REST or the PMC cloud, OAI-PMH or BioC services; PMC prohibits other bulk retrieval (<https://pmc.ncbi.nlm.nih.gov/tools/openftlist/>) |
| **UGA PEDB "Weight Training"** (Pressbooks open book) | University of Georgia | CC BY 4.0. <https://open.online.uga.edu/weighttraining/>, opened by the owner in a browser on 2026-11-13, links <https://creativecommons.org/licenses/by/4.0/>; the site returns HTTP 403 to automated fetches, so no wording is quoted | Attribution, link to the licence, changes marked | Not done: authors and any upstream work unread; accepted by the owner on the licence as stated | G1, possibly G3 | Unread; a search summary gives seven sections (terms and principles, fundamentals, push and pull, compound exercises, periodization). HTML, with Pressbooks exports if offered | Dated snapshot with a SHA-256 of what was taken; fetched by hand, since scripts are refused |
| **HHS Physical Activity Guidelines for Americans, 2nd ed.** | HHS / ODPHP | Public domain. <https://odphp.health.gov/copyright-policy>: "is in the public domain. This means it may be freely distributed and copied — but please include a link to our website and acknowledge ODPHP as the source." The PDF's own front matter has no copyright line (checked, text of all 118 pages) and credits no outside photographs | The acknowledgement is a request; the same page warns that "illustrations, photographs, and other resources contributed or licensed by private sources ... may be protected": the PDF's text has none, figures are not ingested | US federal authors (see Acknowledgments page of the PDF); chapters 4, 5, 7 cover adult muscle-strengthening, gradual progression, injury risk | G5 (settles the "unverified" in note 11) | 118 pages, about 40,000 words, PDF | URL <https://odphp.health.gov/sites/default/files/2019-09/Physical_Activity_Guidelines_2nd_edition.pdf>, SHA-256 `0147d4dfc5ae76613a8b8d9d1c95244477527989f1d841845866ae5b5340cda5` (fetched 2026-11-13, 15,360,711 bytes) |
| **US Army FM 21-20, Physical Fitness Training (1992, Change 1 of 1 Oct 1998)** | Headquarters, Department of the Army | US government work. The Change 1 transmittal prints "DISTRIBUTION RESTRICTION: proved for public release; distribution is unlimited." (OCR of "Approved"). Read in the Elon ROTC copy, <https://elon.edu/assets/docs/rotc/FM%2021_20%20Physical%20Fitness%20Training.pdf>; I did not find the Army's own copy (a search lists the manual as superseded in 2010 by TC 3-22.20), so the licence rests on 17 U.S.C. 105 and the distribution line | None in law; cite the manual | Army-authored; no copyright or permission text in the whole extract (`grep` found none). Third-party drawings not checked | G1 (weight training principles, spotting, injuries chapter, warm-up, flexibility), G5 | 241 pages, about 63,000 words, scanned OCR with errors, so a cleaning pass is needed; dated (1992) | SHA-256 `175319e43d1b5271f8149f3b7ce06b33c8d49a8e84653a74f03363d64f02e3b8` of the Elon file (fetched 2026-11-13) |
| **ISSN position stands** (protein 2017, creatine 2017, caffeine 2021, nutrient timing 2017), only if nutrition is brought into scope | International Society of Sports Nutrition, via BMC | CC BY 4.0. <https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0173-z>: "distributed under the terms of the Creative Commons Attribution 4.0 International License" | CC BY as above | Original position statements | G7 only | about 20 to 40 pages each | DOI (10.1186/s12970-017-0173-z, 10.1186/s12970-017-0177-8) + PMC id (PMC5469049, PMC5477153) |

Articles checked on the publisher's page (licence read) and worth a look, each by topic. The Europe PMC search that found them is `LICENSE:"cc by" AND OPEN_ACCESS:y AND <title terms>`, sorted by citations (<https://www.ebi.ac.uk/europepmc/webservices/rest/search>).

| Topic | Article (DOI) | Licence read on |
|---|---|---|
| Range of motion from resistance training | 10.1007/s40279-022-01804-x | Springer |
| Foam rolling, performance and recovery | 10.3389/fphys.2019.00376 | Frontiers |
| Deep squat and the knee | 10.3389/fspor.2024.1477796 | Frontiers |
| EMG of the deadlift and its variants | 10.1371/journal.pone.0229507 | PLOS |
| Bench press grip width | 10.3390/ijerph18126444 | PMC copy of the MDPI notice |
| Neuromuscular warm-ups against injury | 10.1186/1741-7015-10-75 | BMC (CC BY 2.0) |
| Cold water immersion and soreness | 10.1007/s40279-015-0431-7 | Springer |
| Resistance exercise dose for tendinopathy | 10.1136/bjsports-2022-105754 | PMC copy of the BMJ notice |
| Isometric exercise for tendinopathy | 10.1136/bmjsem-2020-000760 | PMC copy of the BMJ notice |
| Nordic hamstring volume | 10.1007/s40279-019-01178-7 | Europe PMC licence field only; open the Springer page before use |
| Squat, bench, deadlift kinematics under fatigue | 10.1186/s40798-025-00921-x | Europe PMC licence field only; open the BMC page before use |

Rules that make this safe to automate: take only articles whose licence is exactly CC BY or CC0 (PMC lists CC BY-ND among "commercial use allowed"; a verbatim redistribution under ND is arguable, so exclude it too: <https://pmc.ncbi.nlm.nih.gov/tools/textmining/>); keep the licence string recorded at fetch time per article; strip figures, tables and reference lists as the corpus already does for Wikipedia. Europe PMC's licence field comes from PMC's own metadata, so the check on the publisher's page above is the one to repeat for every article that enters.

## 3. Rejected

| Source | Reason | Evidence |
|---|---|---|
| OpenStax Anatomy and Physiology 2e | CC BY-NC-SA, and "ingested into large language models" barred without prior written permission | <https://openstax.org/books/anatomy-and-physiology-2e/pages/preface>: "licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0" |
| RepDB exercise dataset (GitHub, Hugging Face) | custom licence: attribution link required, "No redistribution as a dataset" | <https://raw.githubusercontent.com/RepDB/exercise-dataset/main/LICENSE-DATA.md> |
| `hasaneyldrm/exercises-dataset` (1,324 exercises, 6 languages) | instruction text "MIT" by the repo's author, but the text is stock model-style prose ("Repeat for the desired number of repetitions") with no named author or upstream, the Italian is machine-translated, and the media belongs to Gym visual; an exact-phrase web search found no source, so provenance cannot be shown | <https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/NOTICE.md> |
| EU-OSHA publications (Italian prevention texts) | no named open licence: "La riproduzione e autorizzata con citazione della fonte, salvo indicazione contraria", overridden wherever prior authorisation is required | <https://osha.europa.eu/it/legal-notice> |
| HPRC (hprc-online.org) | no copyright or public-domain statement found; the legal page asks only for attribution and says content is for education; the site is run by a university consortium and may include contractor text | <https://hprc-online.org/about-us/legalmedia> |
| Wikibooks, Wikiversity (it, en) | already judged tiny or off topic; a fresh search for weight-training books on it.wikibooks / it.wikiversity found only an athletics "Potenza" page of about 10 KB | <https://it.wikibooks.org/w/api.php> (search API) |
| Italian-language CC BY articles on PMC | none found: Europe PMC's `LANG:ita` hits are English articles tagged Italian by abstract, and Italian-title queries ("allenamento", "attivita fisica", "esercizio fisico") returned 0 open-access results | <https://www.ebi.ac.uk/europepmc/webservices/rest/search> |

## 4. Not verified

None of these is assumed open; each needs a human with a browser, or a different route.

| Source | What I found | Why not settled |
|---|---|---|
| NIA (NIH) exercise pages, "Go4Life" strength exercises | A search-engine summary says the NIA policies page, <https://www.nia.nih.gov/about/policies>, calls website text public domain with a credit request, and stock photos not licensed; I did not read the page itself | the site answers automated requests with HTTP 405 or a human-verification page; Wayback Machine also blocked bulk requests (HTTP 429), so no archived copy was read. Even if the wording holds, the text (about 10 pages) is not deeper than what Wikipedia already has on general strength |
| Ministero della Salute (salute.gov.it) | The legal notice, <https://www.salute.gov.it/new/it/altro/note-legali-2/>, read in a browser by the owner on 2026-11-13: "I contenuti pubblicati sul presente sito www.salute.gov.it sono messi a disposizione con licenza CC-BY 4.0 - Attribuzione." A search summary adds, unread: open data under IODL 2.0, images, logos and third-party material excluded, some thematic sub-sites on CC BY 3.0 | the site licence is settled: CC BY 4.0. Still open, per document: the Ministry's 2021 *Linee di indirizzo sull'attivita fisica* follows the WHO 2020 guidelines, which are CC BY-NC-SA IGO, so the PDF may be a derivative that the site-wide CC BY cannot clear |
| MHCC "Introduction to Exercise Science for Fitness Professionals" | A search summary says CC BY 4.0 and "a clone of another open text": <https://mhcc.pressbooks.pub/hpe172/> | HTTP 403; the upstream is unnamed, and the earlier Markell/Flynn finding shows why that matters |
| Navy NOFFS strength guides | The Navy hosts them on med.navy.mil; they were produced with a contractor (Athletes' Performance Institute, per trade press) | the PDF link returned an HTML error page; no licence line read; contractor text may be copyrighted |
| NIOSH *Ergonomic Guidelines for Manual Materials Handling* (2007-131); NIAMS, NCCIH pages | CDC's own page says most of its content "is not subject to copyright, is in the public domain, and may be freely used or reproduced", with exceptions for contractor and third-party work (<https://www.cdc.gov/other/agencymaterials.html>) | the NIOSH document and the NIH institutes' policy pages were blocked, so the document itself was not checked for a contractor or third-party clause |
| Physiopedia | its pages and policy pages are behind Cloudflare; a search summary found no named licence for page text and a separate AI-training licensing letter | licence unknown; treat as out until read |
| A translated corpus | Not a source: CC BY and public-domain English texts may legally be translated (CC BY allows adaptation if marked). The map already chose query translation over corpus translation (<../work/answer-from-sources/issues/02-italian-questions-english-texts.md>) | a decision for the owner, not a licence question |

## 5. Ranked recommendation

Coverage per unit of ingestion effort, and the honest limit of each:

1. **HHS Physical Activity Guidelines, 2nd ed.** One PDF, public domain on the publisher's page, a pinned hash. Fills part of G5 (days per week, gradual progression, injury risk). Smallest effort; gives sourced numbers, not technique.
2. **A hand-picked set of CC BY reviews** (section 2, the table of eleven DOIs as the start). Only route to G5 with dose-response numbers, to injury-prevention evidence and to recovery modalities (G4: foam rolling, cold water). Effort: moderate, a fetch step through Europe PMC or the PMC cloud with a per-article licence check, then the same prose-only cutting as Wikipedia. Limit: research prose, not cues; it will not fix G1 or G3.
3. **FM 21-20 (1992/1998).** Public domain by authorship. Adds weight-training principles, spotting, warm-up, flexibility and the injuries chapter in the Army's voice, overlapping ATP 7-22.02. Effort: highest of the three, because the scan is OCR text. Low marginal value.
4. **UGA PEDB "Weight Training".** CC BY 4.0, read by the owner. The only candidate for G1 (technique cues). Effort: a manual download, since the site refuses scripts; its content and size are still unread, so its value is unmeasured.
5. **Settle by hand, in a browser:** NIA and the Ministry's legal notice.

No verified open source fills G2 (Italian technique) or G3 (named accessory exercises) or G6 (programme brands). The honest options are to accept them as *not covered*, or to widen Italian Wikipedia by hand-picked pages as in note 11. G7 is out of scope.

## 6. PDF books, checked 2026-11-13

Each PDF was downloaded and its front matter read; hashes are of the file fetched.

| Book | Licence as read in the PDF | Verdict | Gap | Size | Pin |
|---|---|---|---|---|---|
| *The Navy SEAL Physical Fitness Guide*, ed. P. Deuster, USUHS, Aug 1997: <https://champ.usuhs.edu/sites/default/files/2020-03/navysealfitnessguide.pdf> | No copyright notice; edited at a federal university, chapter authors are Navy medical officers; DTIC record ADA524159 is marked approved for public release (search summary, record not opened) | In, chapters 6-9 and 12 (strength training, flexibility, calisthenics, plyometrics, injuries). Out: Appendix A (weight-lifting instructions) and two tables in chapter 6, printed as "adapted with permission from *Strength Training for Sports*, Applied Futuristics" | G1, G5 | 306 pages, about 70k words, clean text | SHA-256 `f80847e912d53f07d5480a080d4348fc07cac2aedbd75095177e00fdac12ca40` |
| *Exercise & Physical Activity: Your Everyday Guide*, National Institute on Aging, NIH publication 09-4258 | No copyright notice in the PDF; an NIH publication, so a US government work by authorship. NIA's own policy page is still unread (section 4), and the copy read is a mirror: <https://geriatrictoolkit.missouri.edu/consumer/Exercise_and_Physical_ActivityYour_Everyday_Guide_from_The_NIA.pdf> | In on authorship, text only (photos are a contractor's). Numbered steps for about 40 strength, balance and flexibility exercises, written for older adults | G1 | 124 pages, about 23k words | SHA-256 `62876c2cee2eee05c80981c80dc120029574218772d34c7af346c7ad9d7282f5` |
| *Bridging Science and Practical Appliance in Resistance Training*, IntechOpen 2023: <https://mts.intechopen.com/storage/books/12191/authors_book/authors_book.pdf> | "Individual chapters of this publication are distributed under the terms of the Creative Commons Attribution 3.0 Unported License"; the compilation as a whole is reserved | Out on content: seven chapters on school children, pregnancy, older adults and health, no lifting technique. Chapter 4 (musculoskeletal) is the only one near scope | G5 at most | 162 pages, about 56k words | SHA-256 `6cd76b9844bf51afeeff42788c78360577caebbab0d5e82ff2346a49d2138d9d` |
| *Peak Performance Through Nutrition and Exercise*, USUHS 1999: <https://champ.usuhs.edu/sites/default/files/2020-03/ergopam.pdf> | No copyright notice; diagrams "adapted ... with permission from Fred Koch" | Out: mostly nutrition, and its strength chapter repeats the SEAL guide | none | 133 pages, about 35k words | not pinned |
| *Growing Stronger: Strength Training for Older Adults*, CDC and Tufts, 2002 | A search summary says the PDF carries a Tufts copyright and allows copying only unaltered; CDC Stacks labels it public domain (<https://stacks.cdc.gov/view/cdc/11447>). PDF not opened | Out: the two statements conflict, and "unaltered" rules out cutting it into chunks | | | |

No open Italian book was found: the search returned commercial textbooks, theses and federation handouts with no licence.

### Licence check of the two books kept

| | *Navy SEAL Physical Fitness Guide* | NIA *Your Everyday Guide* |
|---|---|---|
| Statement in the PDF | none: no copyright line, no reuse line, no distribution statement | none |
| Statement on the publisher's site | none found: <https://champ.usuhs.edu/> and <https://www.usuhs.edu/legal-and-administrative> carry no copyright or reuse wording; the DTIC record returned HTTP 403 | unread: NIA's site refuses automated requests |
| Authors of what would be taken | chapter 6: P. Deuster, USUHS faculty; chapters 7-9: LCDR L. Thorson, Navy; chapter 12: CAPT J. Moore, Navy (the PDF's "About the Authors") | the institute itself; panel members and a writer are named, photos by a contractor |
| Third-party material printed in it | ch. 1 figure from McArdle; ch. 4 tables from *Running Injury-Free* (Rodale); ch. 6 two tables and Appendix A from *Strength Training for Sports* (Applied Futuristics), "with permission" | none marked |
| Basis | US government work by authorship (17 U.S.C. 105), inferred, not stated | the same, inferred |

Both rest on who wrote them, where ATP 7-22.02 and the HHS guidelines rest on a statement read. A later commercial edition of the SEAL guide exists (Simon & Schuster); it is a separate work and is not the file pinned here.

### *The Warfighter's Fitness Playbook 2.0* (US Air Force, Feb 2026)

Read from a copy the owner downloaded by hand (kept outside the repo); the publisher's URL returns HTTP 403 to scripts: <https://www.afpc.af.mil/Portals/70/documents/FITNESS/Tab%204.%20The%20Warfighter's%20Fitness%20Playbook%20%202.0%20Feb%202026.pdf>.

| | |
|---|---|
| Licence | No statement in the PDF: no copyright line, distribution statement, author or third-party credit. Published by the Air Force Personnel Center as Tab 4 of its fitness programme, so a US government work by authorship (17 U.S.C. 105), inferred as for the SEAL guide. Text only; the pictures' origin is not stated |
| Verdict | In |
| Content | Fitness principles, resistance and endurance programming, measuring intensity, reconditioning, working around an injury profile, a 12-week programme; Appendix B, an exercise library of 70 entries (warm-up, training, recovery), each two to five sentences of execution; Appendix H, warm-ups and cooldown stretches described in full |
| Gap | G1 (short execution text for common exercises), G4 (recovery), G5 (programming); nothing for G2 or G3 |
| Size | 72 pages, about 18k words. `pdftotext` output is dirty: page headers and step numbers bleed into the text, so it needs cleaning |
| Pin | SHA-256 `57535a935dba673861f86a13eb0b8ead1001dc1d9e5f9c6fe1a8cd1b44cf4c6f` |
