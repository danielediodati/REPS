# More open sources

Type: research
Status: resolved

## Question

Corpus version 1 rests on Wikipedia, MedlinePlus and free-exercise-db ([Sources and licences](01-sources-and-licences.md)). Technique is thin there: few cues, few common faults, and short steps from free-exercise-db. Which other texts may be redistributed in a public MIT repo and add technique, faults or injury prevention? Check at least:

- US Army FM 7-22, *Holistic Health and Fitness*: a US government work, so presumably public domain. Check its distribution statement and whether figures or excerpts carry third-party rights.
- National Institute on Aging (NIH) strength-exercise pages: public domain, with step-by-step instructions.
- *Introduction to Biomechanics* on Pressbooks (openedmb.ca), listed as CC BY 4.0 but never opened.
- Any Italian source with an open licence beyond Wikipedia.

For each source give its licence, attribution duties, coverage, format and how to pin it. Answer before the eval set is frozen (16.1.5): a source added later costs a refresh and relabelling.

## Answer

Researched 2026-11-08 on branches `research/more-open-sources` and `research/open-fitness-textbooks`; licences read on the publishers' own pages.

| Source | Licence | Verdict |
|---|---|---|
| US Army ATP 7-22.02, *H2F Drills and Exercises* | US government work, public domain | In: chapters 2-5, 9-11, 13-16, pinned by the PDF's SHA-256 |
| wger, Italian exercise descriptions | CC BY-SA 3.0/4.0, CC BY 4.0 or CC0, per entry | In: the only open Italian technique text; pinned by a hash of what was taken |
| More Wikipedia, taken from its categories | CC BY-SA 4.0 | In: 265 pages in all |
| ATP 7-22.01, FM 7-22 | public domain | Out: test administration and programming, not technique |
| NHS | OGL plus a no-charge clause | Out: a condition on the repo's users |
| NIA (NIH) | unverified, the site blocks scripts | Out |
| Markell and Peterson; Shelton | labelled CC BY 4.0 | Out: Markell is a modified version of Flynn's *Concepts of Fitness and Wellness*, which is CC BY-NC-SA, so the CC BY label does not hold; Shelton derives from Markell |
| Flynn; Lumen; Titus; mobilesport.ch; Kallipos | NonCommercial | Out |
| *Introduction to Biomechanics*; Wikibooks; ISS | open | Out: off topic, tiny or wrong |
| free-exercise-db `instructions` (chosen in [Sources and licences](01-sources-and-licences.md)) | labelled Unlicense | Out: the text is bodybuilding.com's, word for word (its Barbell Squat page as archived on 2013-01-06); upstream admits scraping its images |

No open Italian source on technique exists beyond Wikipedia and wger.
