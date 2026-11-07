# How a citation looks

Type: prototype
Status: resolved
Blocked by: 01

## Question

What does an answer with its source look like in Telegram: where the citation sits, what it names (title, section, link), how a refusal reads when the corpus does not cover the question, and how long an answer may be. Make a few rough replies to react to.

## Answer

The passage quoted, then the link. The answer comes first and is short (~150-250 characters). Under it, each passage used is quoted verbatim in an expandable blockquote, in its source's language: an English passage stays English. Under each quote, `Wikipedia (en), «Title» § Section` is a text link to the pinned revision, and the raw URL never shows. A refusal is two lines with no source: it is not in the texts, here is what they cover. When a message also mentions a current pain, the technique part is answered and cited, and the pain goes to triage in a separate sentence.

What follows from this:

- Entrance replies move from plain text to MarkdownV2, with everything escaped, as `offer()` already does.
- A chunk carries its title, section, language and revision link.
- A quote that is not verbatim in a retrieved chunk is something code can catch, before any judge sees it.

Prototype (four variants × four cases) on the branch `prototype/citation-looks`, in `prototype-citation.html`.
