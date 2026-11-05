# Review guide

Every PR is reviewed before it is merged: by a new Claude agent while PR-Agent
is paused (owner, 01.11.2026), otherwise by PR-Agent. The reviewer knows nothing
of the session that wrote the change: it gets the PR's intent, its diff and the
repository, and this file. The owner does not read code; this review is the
second reader. The full rule: `agent.md` of mitori-app.

## What failure looks like here

These data feed the app and the printed booklet. A bug that matters:

- **Wrong programme:** a technique missing, doubled, in the wrong grade or
  order, a wrong name or attack, a video that starts at the wrong place; data
  that differs from `quellen/` without an entry in `KORREKTUREN.md`.
- **Breaks the consumers:** `mitori-daten.json` or the `*.lua` files change
  without `FORMAT` and the app or booklet following.
- **Leaks:** videos, bundle keys or codes in the repository, also encrypted.
- **Lies:** docs or comments the code contradicts; a `STAND` or tag that does
  not match the data it names.

## What to check in particular

- Programme data only in `daten/*.yaml`, checked by `tools/daten.py`; generated
  files (`daten/shinki-toho-kommentare.yaml`, `daten/lexikon.yaml`) not edited
  by hand; every `[ID]` in the data has an entry in `KORREKTUREN.md`.
- A data release changes `STAND` and `CHANGELOG.md` together.
- Bug fixes: a test that failed before the fix, and the cause removed.

## Skip

`quellen/` (originals of the association).

## How to report

- Every finding names file and line and the concrete input or state that
  goes wrong. No guess without evidence; if unsure, say so.
- Each finding gets one label: **Wichtig** (a bug from the list above,
  must be fixed or answered before the merge), **Kleinigkeit** (optional,
  at most five) or **Bestand** (the bug was there before this PR; not
  blocking).
- The report starts with the count, e.g. "2 Wichtig, 1 Kleinigkeit". Only when
  no **Wichtig** is open it says plainly: "Nichts zu beheben."
- Findings in German, code names as they are.
