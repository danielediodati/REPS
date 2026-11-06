# Sources and licences

Type: research
Status: resolved

## Question

Which openly licensed texts cover exercise technique and injury prevention well enough to answer an owner's questions, and may be redistributed in a public repo? Candidates to check include OpenStax *Anatomy & Physiology*, MedlinePlus, Wikipedia and Wikibooks, and free-exercise-db's own `instructions`. For each: licence and its attribution or share-alike duties, coverage (technique cues, common faults, prevention, warm-up), language, size, format and how it can be fetched. Name what is not allowed (ExRx, NSCA and similar) and why.

## Answer

The core is a curated list of English and Italian Wikipedia pages (CC BY-SA 4.0), each pinned by revision id, which also freezes the eval; Italian Wikipedia is the only Italian source found. Support: free-exercise-db `instructions` (Unlicense) and NLM-written MedlinePlus summaries (US public domain); HHS/CDC pages for *how much*, not technique. Not usable: OpenStax *Anatomy & Physiology* 2e (CC BY-NC-SA, NonCommercial), WHO guidelines (CC BY-NC-SA IGO), ExRx, NSCA, Mayo Clinic, A.D.A.M. (copyrighted). Verbatim chunks keep CC BY-SA and go under their own directory with a `NOTICE`; a collection does not make the repo share-alike. Embeddings are unsettled, so vectors are built from the text and not committed. Unverified: free-exercise-db's upstream origin, the HHS PDF's copyright page, Ministero della Salute, a CC BY Pressbooks biomechanics text. Details in `research/answer-sources.md` on branch `research/answer-sources`.
