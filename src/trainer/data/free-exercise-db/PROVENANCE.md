# Provenance

| | |
|---|---|
| upstream | <https://github.com/yuhonas/free-exercise-db> |
| commit | `a859101d633a01c4a1a920d6a8ce41dabba0705f` |
| commit date | 2026-08-30 |
| vendored on | 2026-09-02 |
| license | The Unlicense (public domain) — see `LICENSE.md` |
| records | 876 |
| sha256 of `exercises.json` | `5bb747e3fc658f095a60dcbf6d53c96627acdcc6ffb6fffde86f7e26995d40bf` |
| files | `dist/exercises.json` -> `exercises.json`, `LICENSE.md` |

The dataset is vendored rather than fetched at import time. The import then
needs no network and is reproducible, and the catalog cannot change underneath
the work between one session and the next — which matters most for session 2,
where enrichment runs once and costs real money.

Images are **not** vendored. `images` holds paths relative to the upstream
image directory, resolved against:

    https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/

Bringing a few hundred megabytes of JPEGs into a repo meant to be cloned would
cost more than it returns; the upstream repository is public domain and hosts
them already.

The vendored file is byte-identical to what upstream published at that
commit; `.gitattributes` disables line-ending conversion for this directory so
it stays that way. To check:

    curl -sS --fail -L       https://raw.githubusercontent.com/yuhonas/free-exercise-db/<commit>/dist/exercises.json       | sha256sum

## Re-vendoring

Replace `exercises.json` and `LICENSE.md`, update the commit and date above,
then re-run `trainer db import`. The import removes rows the new dataset no
longer carries, so the table follows the file rather than accumulating
everything the file has ever said.

Use `curl --fail`: without it a 404 is written into the file as if it were the
download, and a fourteen-byte `404: Not Found` is a license file that passes
every check nobody wrote.
