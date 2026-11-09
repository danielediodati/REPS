# Provenance

| | |
|---|---|
| upstream | <https://github.com/yuhonas/free-exercise-db> |
| commit | `a859101d633a01c4a1a920d6a8ce41dabba0705f` |
| commit date | 2026-08-30 |
| vendored on | 2026-09-02 |
| license | The Unlicense (public domain) — see `LICENSE.md` |
| records | 876 |
| sha256 of upstream's `exercises.json` | `5bb747e3fc658f095a60dcbf6d53c96627acdcc6ffb6fffde86f7e26995d40bf` |
| sha256 of the vendored `exercises.json` | `d86924d4640d5ea72e981614f2c9676d6c0f9b5ab4d7aacf94bd4848cb9744cb` |
| files | `dist/exercises.json` -> `exercises.json`, `LICENSE.md` |
| removed | every record's `instructions` and `images` |

`instructions` is removed because it is not upstream's to license: it is
bodybuilding.com's text, word for word (compare `Barbell_Squat` with
<http://www.bodybuilding.com/exercises/detail/view/name/barbell-squat> as the
Wayback Machine archived it on 2013-01-06). `images` is removed for the same
reason: upstream's contributing guide says the pictures were taken from the
internet.

The dataset is vendored rather than fetched at import time. The import then
needs no network and is reproducible, and the catalog cannot change underneath
the work between one session and the next — which matters most for session 2,
where enrichment runs once and costs real money.

The vendored file is upstream's at that commit, with `instructions` and `images` dropped
and the rest written back as upstream formats it. `.gitattributes` disables
line-ending conversion for this directory so it stays byte-stable. To check:

    curl -sS --fail -L https://raw.githubusercontent.com/yuhonas/free-exercise-db/<commit>/dist/exercises.json \
      | uv run python -c "import json,sys; d=json.load(sys.stdin); [(r.pop('instructions'), r.pop('images')) for r in d]; sys.stdout.buffer.write((json.dumps(d,indent=2,ensure_ascii=False)+'\n').encode())" \
      | sha256sum

## Re-vendoring

Replace `exercises.json` and `LICENSE.md`, drop `instructions` and `images` as above,
update the commit, date and hashes above, then re-run `trainer db import`.
The import removes rows the new dataset no longer carries, so the table
follows the file rather than accumulating everything the file has ever said.

Use `curl --fail`: without it a 404 is written into the file as if it were the
download, and a fourteen-byte `404: Not Found` is a license file that passes
every check nobody wrote.
