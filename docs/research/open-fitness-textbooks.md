# Open fitness textbooks and exercise databases

Researched 2026-11-08. Builds on `research/answer-sources` and `research/more-open-sources`. Not legal advice; my interpretation is marked as such. **Unverified** marks anything I could not read on the owner's page.

Access limits: all Pressbooks hosts (`mhcc.pressbooks.pub`, `openwa.pressbooks.pub`, `ecampusontario.pressbooks.pub`, `openoregon.pressbooks.pub`, `pressbooks.pub`) answered 403 to scripts and to the fetch tool. I read the same Shelton book through its CUNY Manifold copy (which shows the book's own copyright and attribution pages) and the Markell book through its LibreTexts mirror. Open Textbook Library (`open.umn.edu`) listing pages mostly did not load.

## Answer

| Source | Licence | Adds | Verdict |
|---|---|---|---|
| **Shelton, *Introduction to Exercise Science for Fitness Professionals*** (MHCC, 2021) | CC BY 4.0 "except where otherwise noted" | Chapters 5 (flexibility, stretching), 7 (core), 9 (resistance training: programming, exercise order, **form basics**) | **Use**, chapters 4, 5, 7, 9 only (the ones attributed to Markell and Peterson) |
| **Markell and Peterson, *Health and Fitness for Life*** (MHCC Library Press, 2019) and its clone *Exercise and Nutrition* (Centralia) | CC BY 4.0 | Same text as Shelton ch. 4, 5, 9; muscular fitness, flexibility, programming | **Use** as the origin of the above; cite the original, not both |
| **wger exercise database** (wger.de API) | Per entry: CC-BY-SA 3.0, CC-BY-SA 4.0 or CC0 | 950 exercises with step-by-step description; **140 in Italian** | **Support**: best Italian find, but ShareAlike and short texts |
| free-exercise-db / wrkout exercises.json | Unlicense | Already known (free-exercise-db) | No new value; wrkout appears to be the same family |
| Flynn et al., *Concepts of Fitness and Wellness* (GALILEO) | **CC BY-NC-SA 4.0** | Wellness, fitness principles | **Reject** (NonCommercial) |
| Kramer, *A Guide to Physical Activity* (UMN) | CC BY 4.0 | Definitions, guidelines, FITT | **Reject** for this gap: no technique, no warm-up, no injury |
| Zenko and Jones, *Exercise and Sport Psychology*; Hamm, *Biomechanics of Human Movement* | CC BY 4.0 (**unverified** on the books) | Psychology; mechanics | **Reject**: off topic |
| Titus *Introduction to Kinesiology*; Lumen *Lifetime Fitness and Wellness*; MacIntosh *Open Textbook of Exercise Physiology*; Ellingson-Sayen *Foundations of Exercise Science* | NC-SA, NC-SA, NC, NC | | **Reject** (NonCommercial) |

**Italian: nothing new.** The only Italian content under an acceptable licence is wger's 140 translated exercises. No Italian open textbook, Federica, INDIRE or university repository gave a CC BY / BY-SA text on weights or kinesiology.

## Shelton, *Introduction to Exercise Science for Fitness Professionals*

| | |
|---|---|
| Licence | "licensed under a Creative Commons Attribution 4.0 International License, except where otherwise noted"; copyright 2021 Amanda Shelton. Read on the book's own copyright and attribution pages ([copyright page, Manifold copy](https://cuny.manifoldapp.org/read/29f07639-3b89-4ad6-a0ae-3719e32fc8db)); the MHCC original is [mhcc.pressbooks.pub/hpe172](https://mhcc.pressbooks.pub/hpe172) (403, unverified directly) |
| Derivation | "Attribution and OER Revision Statement" ([section](https://cuny.manifoldapp.org/read/29f07639-3b89-4ad6-a0ae-3719e32fc8db/section/058f9905-26bc-4a90-937f-bb9ecfea4c21)): derivative of *Health and Fitness for Life* (Markell and Peterson), remixed with *OU Human Physiology* (Ketchum and Bright), *Body Physics: Motion to Metabolism* (Davis) and *Human Anatomy* (Gridi-Papp). The statement gives no licence per source |
| Risk, my reading | Chapters 1 to 3 (anatomy, biomechanics, metabolism) come from the other sources, whose licences I could not confirm (OU Human Physiology: a University of Oklahoma "all rights reserved" notice appeared on a video page, **unverified**). Chapters 4, 5, 7 and 9 sections I read carry "Adapted from Markell and Peterson" lines. Use only sections that carry that line |
| Attribution | CC BY: name the author, the licence, the source URL, and say the text was changed. Keep the per-page "adapted from" lines |
| Useful sections | Ch. 4 *Additional Safety Concerns*; Ch. 5 *Creating an Effective Stretching Program* (static, dynamic, ballistic, PNF; stretch after warm-up; contraindicated stretches); Ch. 9 *Resistance Exercise Programming*, *Exercise Order*, *Types of Resistance Training*, *Basics of Form during Resistance Training* (core stability, knees tracking over toes to avoid valgus, scapular retraction and depression, neutral head, heel loading), *Resistance Training Systems* |
| Not covered | Lift-specific cues (squat, deadlift, bench) and common faults per exercise. The form section is five general points. This is hypertrophy and programming plus flexibility, not technique. The Army ATP 7-22.02 remains the technique source |
| Quality sample | "To avoid this, stretch slowly and in a controlled fashion while holding the stretch for 10 seconds or more." (ch. 5, *Creating an Effective Stretching Program*). Programming ranges (novice 8 to 12 RM, 2 to 3 days a week, 2 to 10% load increase) match ACSM-style guidance. Mainstream, careful, not exhaustive |
| Language, size | English; 97 sections (Manifold section list). Chapters of interest are about 25 short sections |
| Format, fetch | HTML via Manifold. The Manifold API lists the sections (`https://cuny.manifoldapp.org/api/v1/texts/29f07639-3b89-4ad6-a0ae-3719e32fc8db/relationships/text_sections`) but I did not find a body endpoint that answered. Pressbooks offers EPUB, PDF and XHTML exports at `/open/download?type=...` (403 to my scripts, **unverified**); an owner browser download is the safest route |
| Pin | Manifold text `updatedAt` 2024-12-05; keep a SHA-256 of the downloaded export plus the retrieval date |

Verdict: **use**, chapters 4 (safety), 5, 7 (guidelines), 9. Fills flexibility, warm-up placement, programming and general form. Does not fill per-lift technique.

## Markell and Peterson, *Health and Fitness for Life*

| | |
|---|---|
| Licence | CC BY 4.0, copyright 2019 Markell and Peterson, "except where otherwise noted". Original [mhcc.pressbooks.pub/hpe295](https://mhcc.pressbooks.pub/hpe295) (403; licence taken from search summaries of the page, **unverified directly**) |
| Clone and mirror | *Exercise and Nutrition* (Markell, Peterson, Johnson; Centralia College 2023), [LibreTexts mirror](https://med.libretexts.org/Bookshelves/Health_and_Fitness/Exercise_and_Nutrition_(Markell_Peterson_and_Johnson)): CC BY 4.0, source `openwa.pressbooks.pub/cchlth140`. Its chapter 4 (muscle physiology, fibre types, resistance exercise programming, supplements) and chapter 5 (flexibility) are the same text as Shelton's |
| Not the same as | *Concepts of Fitness and Wellness* (NC-SA): the two books have the same chapter titles, but the Markell book is a separate CC BY work. I found no statement that one derives from the other, but the identical chapter order is a reason to ask; **unverified** |
| Quality sample | "Isometric: muscles produce force without changing length, as in planks or wall sits" (paraphrase from the LibreTexts page 4.3 as returned by the fetch tool; check wording at cut time) |
| Verdict | **Use** through Shelton or directly, whichever is easier to download; do not ingest both |

## wger exercise database

| | |
|---|---|
| Licence | Not one licence: each exercise translation carries a licence id. The API `license` endpoint (`https://wger.de/api/v2/license/`) lists CC-BY-SA 3 (id 1), CC-BY-SA 4 (id 2), CC0 (id 3), CC-BY 4 (id 4), ODbL (id 5). README: "Exercise/Ingredient Data: Creative Commons (see individual entries)"; application code AGPL-3.0 ([README](https://github.com/wger-project/wger/blob/master/README.md)). Docs: the initial data "is licensed additionally under a Creative Commons Attribution Share-Alike 3.0" ([docs](https://wger.readthedocs.io/en/latest/)) |
| Measured, 2026-11-08 | English: 950 translations, licence mix 802 BY-SA 4, 128 BY-SA 3, 20 CC0. Italian: **140** translations (32 BY-SA 3, 99 BY-SA 4, 9 CC0); 136 longer than 50 characters; mean description 359 characters |
| Attribution | Each translation has a `license_author` (for Italian: `wger.de`, `FEFFO`, `BFad07`, `drthurlow` and others). BY-SA needs credit to that author, a link to the licence, and an indication of changes |
| ShareAlike, my reading | An adaptation of a BY-SA text must be offered under BY-SA. Verbatim quotes in a retrieved-passage corpus are at most a collection or quotation, not an adaptation of the repo's code, so MIT code is not affected; the corpus files themselves stay BY-SA and the NOTICE must say so. A compatible reading is not certain. **Owner decides**; CC0 and CC BY entries avoid the question |
| Coverage | Name, step-by-step description (HTML), muscles, equipment, category, per-translation licence. Technique cues are in the steps ("keep your back straight"); faults and prevention are rare. Descriptions are short (a few sentences) |
| Quality | Uneven. Italian sample, *Panca piana con manubri*: "Impugnate due manubri e sdraiatevi su una panca. Tenete i pesi vicino al petto ... Lasciare scendere il peso lentamente e in modo controllato." Fine. A typo remains in a title ("presa srtetta"); some Italian entries are translations of text copied from older English sources, mixing "tu", "voi" and infinitive. Italian entries include one imperative ("Suggerimento: assicurati ...") that reads as a translated fragment of an older database; provenance of the original text is not stated, so BY-SA on those is as asserted by the contributor and **unverified** |
| Language | 33 languages including Italian (id 13) |
| Format, fetch | JSON REST API, no key needed for reads: `https://wger.de/api/v2/exerciseinfo/?language=13&limit=200&offset=N&format=json` (5 pages). Plain `curl` with a descriptive User-Agent worked |
| Pin | wger code commit `aba15ef5a9cc8bbea0835a26407bf91155f73ec3` (2026-11-07). The API has no version tag, so store the page JSON with a SHA-256 and the retrieval date. Each exercise has a `uuid` and per-translation `id`; keep them |
| Overlap | The English set overlaps with free-exercise-db (Unlicense); prefer free-exercise-db there because it needs no attribution |

Verdict: **support.** Use for Italian only: it is the only acceptable licence source of Italian exercise descriptions. Filter to translations whose licence is CC0 or CC BY-SA and store `license_author`. Value is modest (140 short entries, no faults, no prevention).

## Other GitHub projects

| Project | Licence | Finding | Verdict |
|---|---|---|---|
| [yuhonas/free-exercise-db](https://github.com/yuhonas/free-exercise-db) | Unlicense (GitHub API) | Already used; English | Known |
| [wrkout/exercises.json](https://github.com/wrkout/exercises.json) | Unlicense (GitHub API); last push 2025-02-16 | "Open Public Domain Exercise Dataset", same format family as free-exercise-db; README advertises a paid 2,500-exercise dataset | No new value; provenance of text not stated |
| RepDB exercise dataset | Own terms: free in apps, attribution required (search summary, **unverified**) | English, German, Spanish; no Italian | Reject |
| wrkout.xyz | Commercial | Paid | Out |

## Other textbooks checked

| Book | Licence read | Finding | Verdict |
|---|---|---|---|
| Flynn et al., *Concepts of Fitness and Wellness* 3e | GALILEO page: "Creative Commons Attribution-NonCommercial-Share Alike 4.0" ([oer.galileo.usg.edu/health-textbooks/4](https://oer.galileo.usg.edu/health-textbooks/4)); LibreTexts also CC BY-NC-SA 4.0. The GALILEO grants collection page shows a CC BY 4.0 label (search summary only, **unverified**) | The book itself is NC-SA, as the expected-SA assumption was wrong. Chapters 4 (muscular strength) and 5 (flexibility) would have fit | **Reject** |
| Kramer, *A Guide to Physical Activity* | LibreTexts: CC BY 4.0 (source open.lib.umn.edu/physicalactivity) | Three chapters: foundations, benefits, nutrition. Only general advice (resistance training at least 2 days a week, FITT). No technique, warm-up or injury | Reject for this gap |
| Zenko and Jones, *Essentials of Exercise and Sport Psychology* | CC BY 4.0 (search summaries; one figure BASES copyright) | Psychology | Reject |
| Hamm, *Biomechanics of Human Movement* (2020) | CC BY (search summary) | Mechanics, not training | Reject |
| Titus, *Introduction to Kinesiology* | LibreTexts: CC BY-NC-SA 4.0 | | Reject |
| Lumen, *Lifetime Fitness and Wellness* | LibreTexts: CC BY-NC-SA 4.0 | | Reject |
| MacIntosh, *Open Textbook of Exercise Physiology* | CC BY-NC 4.0 (search summary) | | Reject |
| Ellingson-Sayen and Taylor-Winney, *Foundations of Exercise Science* | CC BY-NC ([Open Textbook Library](https://open.umn.edu/opentextbooks/textbooks/foundations-of-exercise-science)) | | Reject |
| Cambrian *Fitness for Paramedics* (eCampusOntario) | A derivative of Shelton's book (so CC BY with the same remix caveat) | Not read (403) | Not needed |
| Runk, *Foundations of Kinesiology* | Listed on LibreTexts Sports and Exercise shelf; page returned 404 | Not found | **Unverified** |
| OpenStax *Anatomy and Physiology 2e* | CC BY 4.0 (from my knowledge, not re-read) | Muscle anatomy and physiology; no training | Not needed |

LibreTexts shelves show a licence for the shelf (Health and Fitness: "CC BY-NC-SA 4.0") that differs from several of its books (Markell, Kramer: CC BY 4.0). Read the licence on each book's own page.

## Italian

| Source | Finding | Verdict |
|---|---|---|
| Wikibooks it, university OER, INDIRE | Searches in Italian for pesi, culturismo, chinesiologia, scienze motorie, fisiologia dell'esercizio found only commercial books and federation PDFs with no open licence | None |
| Federica Web Learning (Federico II) | [federica.eu](https://www.federica.eu/) footer: "Copyright 2026 Federica Web Learning, all rights reserved"; no CC statement, no scienze motorie course found | Reject |
| mobilesport.ch | CC BY-NC-SA (already rejected) | Reject |
| FIDAL / CONI technical PDFs | No open licence stated | Reject |
| wger | 140 Italian exercise entries | Support (above) |

## Not allowed

| Source | Why |
|---|---|
| Flynn et al., *Concepts of Fitness and Wellness*; Lumen *Lifetime Fitness and Wellness*; Titus *Introduction to Kinesiology* | CC BY-NC-SA 4.0 |
| MacIntosh; Ellingson-Sayen | CC BY-NC |
| Kallipos, mobilesport.ch | NonCommercial (earlier research) |
| Federica Web Learning | All rights reserved |
| Shelton chapters 1 to 3 (anatomy, physiology) | Source licences not confirmed; leave out |
| Images and figures in every book | Own licences; the plan takes none |

## Open questions

- **Owner download of Markell/Shelton**: someone with a browser should download the MHCC export (EPUB or PDF), read the Copyright page of the original and of `hpe295`, and confirm "CC BY 4.0, except where otherwise noted" before any chunk is cut. I could only read the Manifold copy.
- **Shelton scope**: accept only sections that carry the "Adapted from Markell and Peterson" line? The physiology chapters come from sources whose licences I could not confirm.
- **Does the Markell book derive from Flynn et al.?** The chapter titles are identical to the NC-SA book. If it does, its CC BY label would be wrong. Ask the authors or check the Pressbooks copyright page.
- **wger ShareAlike**: accept BY-SA chunks (recorded in the NOTICE as BY-SA with `license_author`), or take only the 9 Italian CC0 entries? Value of Italian BY-SA content is small either way.
- **Technique gap**: no CC BY source gives per-lift cues beyond the Army ATP 7-22.02 and the thin Wikibooks pages. Hypertrophy and flexibility are now covered by Shelton; technique faults remain the Army manual's job.
