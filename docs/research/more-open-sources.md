# More open sources: technique, faults and prevention

Ticket: `docs/work/answer-from-sources/issues/11-more-open-sources.md`. Researched 2026-11-08. Builds on `research/answer-sources`. Not legal advice; my interpretation is marked as such. Anything I could not read on the owner's page is marked **unverified**.

## Answer

| Source | Licence | Adds | Verdict |
|---|---|---|---|
| US Army **ATP 7-22.02** *H2F Drills and Exercises* (Oct 2020, C1 Sep 2025) | US government work, public domain; "Approved for public release" | Cue-by-cue descriptions of squat, deadlift, bench, lunge, row, press, with form faults, spotter duties, progressions, warm-up (Preparation Drill) | **Use.** Best find: the technique gap, in public domain |
| US Army **FM 7-22** *H2F* (Oct 2020, C2 Aug 2025) | Same | Programming, periodization, rehabilitation and reconditioning; almost no technique | **Support**, parts only. Skip chapter 8 (nutrition, used with permission) |
| US Army **ATP 7-22.01** *H2F Testing* (Mar 2026) | Same | Technique and scoring of strength deadlift, 3RM deadlift, push-up, plank | **Support** (not read in depth) |
| NHS website (UK) strength, warm-up, stretch, knee pages | Open Government Licence v3.0 plus NHS terms | Beginner cues and faults, in plain English | **Support, owner decides**: the NHS terms add a no-charge clause |
| NIA (NIH) strength exercise pages | Text public domain per NIA policy (**unverified**: site blocks scripts) | Chair and wall exercises for older adults | **Support, unverified** |
| *Introduction to Biomechanics* (Pryce, 2022) | CC BY 4.0, except where noted | Physics: kinematics, Newton, momentum | **Reject**: no technique |
| en.wikibooks *Bodybuilding and Weight Training* | CC BY-SA 4.0 (and GFDL) | Per-exercise "Safety tips" and "Mistakes to avoid" | **Reject**: tiny, and at least one page is wrong |
| ISS / EpiCentro (Italian) | CC BY 4.0 "unless otherwise indicated" | Public-health epidemiology, no technique | **Reject** for this gap |
| mobilesport.ch (Swiss federal, Italian) | CC BY-NC-SA 4.0 | Strength training | **Reject**: NonCommercial |

**Italian: nothing beyond Wikipedia adds technique.** Details in the last section.

## US Army H2F manuals

### Licence

| Point | Finding | Source |
|---|---|---|
| Rule | "Copyright protection under this title is not available for any work of the United States Government" | [17 U.S.C. 105](https://www.copyright.gov/title17/92chap1.html) |
| Distribution statement | FM 7-22 C2: "Approved for public release; distribution is unlimited." ATP 7-22.02 and 7-22.01: same wording | Title pages of the three PDFs below |
| Author | Headquarters, Department of the Army (government authors) | Title pages |
| Third-party text | FM 7-22 Acknowledgements: "The copyright owners listed here have granted permission to reproduce material from their work." The only owner named: chapter 8 nutrition details, with permission from Deuster et al., *Special Operations Forces Nutrition Guide*. ATP 7-22.02 and 7-22.01 carry the same generic sentence and name no owner | Acknowledgements pages |
| Photos | "developed by the U.S. Army Center for Initial Military Training and produced at the Enterprise Media Center" (government). The plan takes no images anyway | Same |
| Attribution | None required by law. My choice: credit "US Army, ATP 7-22.02" with the change date, as the NOTICE does for MedlinePlus | Mine |

My reading: the whole text is public domain except what the Acknowledgements flag. Excluding FM 7-22 chapter 8 and the "Source Notes" quotations removes the named exception. The generic permission sentence in the two ATPs names no owner, so I could not rule out a small quoted item. **Unverified** for that residue; ATP 7-22.02 chapters 1 to 14 are Army-written exercise text.

### Editions and pins

The armypubs file names change with every change, and old ones return an HTML "404" page with HTTP 200 (the earlier `ARN30964-FM_7-22-001-WEB-4.pdf` does). Pin by SHA-256 plus the details page.

| Pub | Edition | Details page | PDF | Size | SHA-256 |
|---|---|---|---|---|---|
| FM 7-22 | Oct 2020, incorporating C2, 1 Aug 2025 | [PUB_ID 1020968](https://armypubs.army.mil/ProductMaps/PubForm/Details.aspx?PUB_ID=1020968) | [ARN44522-FM_7-22-002-WEB-7.pdf](https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN44522-FM_7-22-002-WEB-7.pdf) | 4.3 MB, 240 pp | `FA298E52...98B0B6` (full: `FA298E5287117A0CA7080B950D1D8236B7E34B2A4A3435CE8058CDD4FA98B0B6`) |
| ATP 7-22.02 | Oct 2020, incorporating C1, 16 Sep 2025 | [PUB_ID 1020967](https://armypubs.army.mil/ProductMaps/PubForm/Details.aspx?PUB_ID=1020967) | [ARN45013-ATP_7-22.02-001-WEB-4.pdf](https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN45013-ATP_7-22.02-001-WEB-4.pdf) | 16.2 MB, 254 pp | `58C715B5...875D8A` (full: `58C715B52DF72C5D1FBDEE2A1CA2DD9E6FA3B5B66CC1D88042ABA895B0875D8A`) |
| ATP 7-22.01 | 12 Mar 2026 (replaces Oct 2020) | [PUB_ID 1032672](https://armypubs.army.mil/ProductMaps/PubForm/Details.aspx?PUB_ID=1032672) | [ARN46104-ATP_7-22.01-000-WEB-1.pdf](https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN46104-ATP_7-22.01-000-WEB-1.pdf) | 9.9 MB, 118 pp | `0279C18EACA42D0C790596EDDA2C258C59679903F7EF2A6E25DDAA28743E0AF2` |

Fetch: plain `curl` with a descriptive User-Agent worked. `pdftotext -layout` extracts clean text. The armypubs host and `media.defense.gov` refused `WebFetch` (403). I found the FM 7-22 PDF URL through the Army.mil [H2F publications update](https://www.army.mil/article/295085/h2f_system_update_doctrine_publications_update), not the details page.

Quirks seen in the PDFs: the ATP 7-22.02 contents page still reads "SIGNATURE DRAFT - NOT FOR IMPLEMENTATION"; some page footers keep the 2020 or 2022 date; the extracted text has mojibake for bullets and apostrophes, so the cutter must normalise it. The 2025 changes removed Pose Method running content and renamed the ACFT to AFT.

### Coverage

| Pub | What it holds for us |
|---|---|
| ATP 7-22.02 | Chapter 14 *Free Weight Training*: Front Squat, Back Squat, Deadlift, Sumo and Straight-Leg Deadlift, Bench Press (bar, dumbbell, kettlebell, decline), more. Chapters 5, 11, 13 cover conditioning, landmine and circuit strength drills (single-leg deadlift, lunge, row, push-press, pull-up). Chapter 3 holds the Preparation Drill (warm-up) and Chapter 1 explains how to modify it. Each exercise has a numbered paragraph with the start position, movement, cues ("Maintain a natural arch in the lower back", "Keep the knees aligned over the feet and the heels on the ground", "Do not round out the upper back") and a spotter paragraph. 92 lines carry "Avoid / Do not / Keep the". Sample, Back Squat: "Initially do not squat deeper than 90 degrees. Progress to deeper positions as strength improves. Always lift a weight that can be controlled." |
| FM 7-22 | Doctrine: principles, periodization (ch. 5), program design (ch. 6), physical readiness (ch. 7), reconditioning and rehabilitation (ch. 12). It names squat, deadlift and bench as the core lifts (6-16) but gives no cues. 137 lines mention injury, mostly programming. Mental, sleep, spiritual and nutrition chapters are off topic |
| ATP 7-22.01 | The strength deadlift, 3RM deadlift, hand-release push-up and plank, with a "proper technique" figure and scoring. Not read beyond the contents |

Language: English. Gaps: no Italian; military framing (Soldier, ACFT/AFT) must be tolerated in quotes; spotter and barbell cues are good, but there are no cues for pull-ups beyond the circuit text. Overlap with Wikipedia is small: Wikipedia explains, the Army text instructs.

Verdict:

- **ATP 7-22.02: use.** Chunk by exercise paragraph, from chapters 5, 11, 13 and 14, plus the Preparation Drill.
- **FM 7-22: support.** Take chapter 6 and chapter 12 for injury and rehabilitation framing if wanted; skip chapter 8.
- **ATP 7-22.01: support.** Technique of the deadlift and push-up for tests.

## NHS website (UK)

| | |
|---|---|
| Licence | "Copyright and database rights in NHS Website Content are released free-of-charge under the current version of the Open Government Licence ... You can use NHS Website Content ... including copying it, adapting it, and using it for any purpose, including commercially" (terms 3.3 to 3.4). [Terms](https://www.nhs.uk/our-policies/terms-and-conditions/) |
| Exclusions | Logos, images with identifiable people, stock images, third-party information (3.5). Take no images |
| Attribution | Unchanged copy with a copy date (3.6a): "Information from the NHS website ... as at DDMMYY", linked to the source page, plus a visible statement "Information from the NHS website is licensed under the Open Government Licence v3.0". Adapted or non-refreshed copies must not name the NHS and use "Contains public sector information licensed under the Open Government Licence v3.0." Translation counts as an adaptation |
| Extra terms | 3.10: "no specific charge may be levied on any customers or users for access to any NHS Website Content". 3.11: no implied NHS endorsement. 3.8: no use that brings the NHS into disrepute. NHS terms take precedence over the OGL |
| Why it matters | OGL v3.0 alone fits CC BY 4.0, but 3.10 is a restriction on anyone who charges for access. It does not forbid commercial use, but "anyone may use it commercially" is then not quite true for these chunks. **My reading, not legal advice** |
| Coverage | [Strength exercises](https://www.nhs.uk/live-well/exercise/strength-exercises/) (sit-to-stand, mini-squats, calf raises, leg lifts, wall press-up; cues such as "Keep your back straight at all times", "Avoid arching your back"), [How to warm up](https://www.nhs.uk/live-well/exercise/how-to-warm-up-before-exercising/), stretching, knee exercises, running injuries. Beginner and home level, not barbell technique |
| Format, fetch | HTML, 200 OK to a plain User-Agent, `robots.txt` permits general crawling. Pin by copy date and a hash of the extracted text; the page has no revision id |
| Language | English |

Verdict: **support, owner decides.** Content is good for faults and prevention at a gentle level, but the no-charge clause is a condition on the repo's users. If accepted, record it in the NOTICE.

## NIA / NIH

| | |
|---|---|
| Licence | **Unverified on the owner's page.** `nia.nih.gov` (and `order.nia.nih.gov`) answered every script request with a CAPTCHA page (HTTP 405), and `nih.gov` web-policies returned 403. A search summary of the [NIA policies page](https://www.nia.nih.gov/about/policies) says text is public domain unless marked, asks for credit to "National Institute on Aging, National Institutes of Health", and warns that photos and illustrations are a mix of copyrighted and copyright-free, and that stock photos need permission. I did not read this page myself |
| Coverage | Sample strength exercises for older adults (wall push-up, chair stand, arm raise) with numbered steps and rep counts, plus the general rule of at least two days a week. The old Go4Life site (`go4life.nia.nih.gov`) no longer resolves from my network |
| Fetch | Not scriptable: CAPTCHA. Would need a manual copy from a browser, with a retrieval date |

Verdict: **support, unverified.** Same level as NHS (gentle), and the bot cannot refresh it. Not worth a hand-copied chunk set unless the owner opens the policy page and confirms it in a browser.

## *Introduction to Biomechanics* (Pressbooks)

| | |
|---|---|
| Licence | "Introduction to Biomechanics Copyright (c) 2022 by Rob Pryce is licensed under a Creative Commons Attribution 4.0 International License, except where otherwise noted." Read on a Wayback copy of the book's own landing page, [2026-05-09](https://web.archive.org/web/20260509140413/https://pressbooks.openedmb.ca/introtobiomechanics/). The live host `pressbooks.openedmb.ca` returns 403 to scripts |
| Content | Adapted from OpenStax *College Physics* (Urone and Hinrichs, CC BY) and other OpenStax texts. Chapters: units, 1-D and 2-D kinematics, Newton's laws, work and energy, momentum, angular kinematics, with problem sets |
| Fit | Physics of human movement. No lifting technique, faults or prevention |

Verdict: **reject** for relevance. The licence is fine; the content is not what the gap needs.

## Other candidates

| Source | Licence | Finding | Verdict |
|---|---|---|---|
| en.wikibooks *Bodybuilding and Weight Training* | [CC BY-SA 4.0 and GFDL](https://en.wikibooks.org/wiki/Wikibooks:Copyrights) | 14 pages. Squats, Deadlift (rev 4417640, June 2024), Bench Presses, Dumbbell Flys and Curls each have "Safety tips" and "Mistakes to avoid". The Deadlift page says "Avoid lowering the weights too far below your chest level to prevent shoulder strain" and "Keep a slight bend in your elbows", which is fly advice pasted into the wrong exercise. About 15 kB in all. The earlier research missed this book | Reject. It could be a support if every page were hand-vetted, which costs more than it gives |
| HHS *Physical Activity Guidelines*, 2nd ed. | Federal; the PDF's first pages carry no copyright notice | Dose only, no technique | Not needed |
| NIOSH manual lifting guidance | US government (unchecked) | Occupational lifting, not training | Not pursued |
| US Navy NOFFS | App stores show "(c) CNIC 2014/2017"; site terms not found | Navy workout and exercise descriptions exist, but the copyright claim is unclear | Reject until terms are read (**unverified**) |
| Open textbooks on strength training | | Kallipos *Strength Training* is CC BY-NC-SA and Greek. I found no CC BY or CC BY-SA text on lifting technique | None |
| Wikiversity (en) | CC BY-SA | Search for resistance-training technique returned no page | None |

I did not check VA, Air Force or Marine Corps guides in depth; the Army manuals already fill the gap.

## Italian

| Source | Licence and finding | Verdict |
|---|---|---|
| ISS and EpiCentro | [iss.it/contatti](https://www.iss.it/contatti), "Informazioni legali": "Salvo ove diversamente indicato, i dati e documenti pubblicati sul presente sito sono messi a disposizione con licenza CC-BY 4.0", followed by a caveat that some works "non potrebbero essere riutilizzate" for commercial ends. [EpiCentro](https://www.epicentro.iss.it/chi-siamo/disclaimer) follows the ISS policy, but its BEN section is [CC BY-NC-ND 4.0](https://www.epicentro.iss.it/ben/privacy). The [Attivita fisica](https://www.epicentro.iss.it/attivita_fisica/) pages are epidemiology and policy | Reject: no technique. Also the commercial caveat is ambiguous |
| Ministero della Salute | `salute.gov.it` served a bot challenge (Gcore) to scripts. Licence **unverified**; the earlier research also found none | Reject until a licence is found |
| mobilesport.ch (BASPO, Swiss Confederation) | [Rechtliches](https://www.mobilesport.ch/rechtliches/): texts "fur nicht-kommerzielle Zwecke" under CC BY-NC-SA 4.0; photos excluded. It has Italian strength-training PDFs | Reject: NonCommercial |
| it.wikibooks | CC BY-SA. Searches for fitness and weights found one page, *Atletica leggera/Consigli/Potenza* (revision 434049, 11 kB), a general power-training tip page that mentions warm-up | Reject: not worth the entry |
| Regional health services, CONI, Italian open textbooks | Not found. A web search turned up none with an open licence on lifting technique | None |

**Italian has no source beyond Wikipedia that adds technique.** Options that remain: Italian questions over the English chunks (ATP and NHS give an English passage; translating it at query time is an adaptation, free for public-domain text, but for NHS it triggers the OGL adaptation attribution), or accept thin Italian.

## Not allowed

| Source | Why |
|---|---|
| mobilesport.ch | CC BY-NC-SA 4.0 |
| EpiCentro BEN section | CC BY-NC-ND 4.0 |
| Kallipos *Strength Training* | CC BY-NC-SA 4.0 (from the earlier research) |
| US Navy NOFFS | Copyright notice by CNIC on the apps; terms not read |
| Images from every source above | Own licences; the plan takes none |
| FM 7-22 chapter 8 | Used with permission from Deuster et al., not government text |

## Open questions

- NHS clause 3.10 (no charge for access to the content): acceptable for a corpus whose users may be commercial? If not, drop NHS.
- NIA: someone must open the policy page in a browser (the site blocks scripts) before any chunk is copied.
- ATP 7-22.02: ask whether the generic "copyright owners listed here" sentence hides a quoted item. A diff of its Source Notes pages against the chunks cut would show it.
- Cutting from the PDFs: the extracted text has encoding noise; the cutter needs a normalisation step and a test.
- Which edition to pin: the pins above are the current ones on 2026-11-08; a new Army change replaces the file name, so the manifest should store the SHA-256 and keep the local copy until the refresh.
- Are chunks of a US-government work "verbatim with a NOTICE" enough, or should the NOTICE add a line saying they are public domain and not under MIT or CC BY-SA?
