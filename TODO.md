# TODO / Known issues

Dev-facing notes (not user docs — README stays the user doc).
Entry format: symptom → evidence → workaround → revisit-when → proposed fix.

## Open

### Stats jobs pile up and keep running after "Show only till here"

**Status:** diagnosed 2026-11-09 · deliberately deferred (low urgency, self-healing)

**Symptom:** load ~5000 commits ("Load 100 more"), then right-click →
"Show only till here" on the 10th commit. Only 10 commits are shown, but the
tool stays sluggish for ~1 more minute.

**Measured** (offscreen run on the vim repo, 24.7k commits):

| checkpoint | `git log --shortstat` jobs | CPU | RSS | list |
|---|---|---|---|---|
| after loading 5000 | 16 | 651% | 130 MB | 5001 |
| immediately after shrink | 17 | 630% | 130 MB | 11 |
| +7s | 15 | 626% | 131 MB | 11 |
| +17s | 14 | 602% | 132 MB | 11 |
| +32s | 9 | 427% | 134 MB | 11 |
| drained | 0 | idle | — | ~50s after shrink |

Memory is *not* involved (RSS flat); loading 5000 itself took 125s because
each click spawns another stats job that starves the UI.

**Root cause:** `_load_stats_async()` (`lib/app_window/rescan_mixin.py`) spawns
an uncancelled daemon thread running `git log <base>..HEAD --shortstat` for the
*whole* range on every load, and creates a new 50 ms `QTimer` without stopping
the previous one (~52 orphaned timers in one session). Nothing cancels stale
jobs on reload/shrink.

**Workaround (zero risk):** View → **Show Stats** off before bulk-loading —
`_load_stats_async` is gated on `self.show_stats` (`rescan_mixin.py:457`).

**Revisit when:** loading 5k+ becomes routine and the ~1 min drag annoys, or a
long session gets sluggish on its own (timer pile-up).

**Proposed fix, in slices:**

1. *low risk, ~6 lines:* stop the previous stats timer + generation token so
   stale results can't clobber the current load (no process killing).
2. *separate, needs tests:* cancel the superseded `git log` (Popen + terminate)
   so CPU frees immediately on shrink.
3. *optional:* incremental stats per "Load 100 more" (currently quadratic:
   100+200+…+5000 ≈ 1.25M commit-stats work).

### Permission hurdles on a repo created by a different user

**Status:** reported 2026-11-09 · not yet diagnosed (no reproduction captured)

**Symptom:** opening the tool on a repository owned by another user sometimes
runs into permission problems — history fails to load or operations error out,
and the failures surface as generic git errors rather than telling you what is
actually wrong.

**Likely culprits (to confirm when diagnosing):**

- git's *"detected dubious ownership in repository"* refusal — the classic when
  the repo's owner differs from the invoking user (`safe.directory` not set)
- `EACCES` on `.git/` internals (objects, refs, index) when the repo or parts
  of it are not readable/writable by the current user
- the tool's own writes failing: settings (`QSettings`), logs, update cache —
  `lib/unclean_exit.py:97` is the only `PermissionError` handled anywhere; git
  helper failures are logged generically and surfaced as plain error dialogs

**Workaround:** `git config --global --add safe.directory <repo-path>` for the
ownership case; otherwise fix ownership/permissions on the repo
(`chown`/`chmod`) or run the tool as the repo's owner.

**Revisit when:** it happens again — capture the exact git stderr / dialog text
and the repo's `ls -ln .git` at that moment, then promote this entry from
"reported" to diagnosed.

**Proposed fix (once diagnosed):**

1. detect git's `dubious ownership` stderr specifically and offer to add the
   path to `safe.directory` (with explicit confirmation — it is a security
   setting), instead of a generic failure
2. detect `PermissionError`/`EACCES` from git and from the tool's own file
   writes, and report the offending path + required permission
3. fail fast at startup with one clear message when the repo is unusable,
   rather than a sequence of empty lists and error dialogs
