# Workflow

After non-trivial changes, run a review-fix loop with the `code-reviewer`
subagent until it returns clean:

1. Spawn `code-reviewer` on the changed files.
2. Apply the fixes that are real (skip nits unless they hide a bug).
3. Re-spawn `code-reviewer`, telling it which prior issues are already
   addressed so it doesn't re-flag them.
4. Stop when the reviewer says clean.

# Verification

Don't claim something works from assumptions — verify against ground truth and
state confidence honestly, flagging what's unverified. The Fire TV is reachable
via `adb` (address in `config.toml`): validate parsing/playback against real
`dumpsys` output, and check prod logs (`journalctl -t rpimedia-cron`) before
declaring a fix confirmed.

# Dependencies

Add/remove Python deps with `uv add` / `uv remove`, never by hand-editing
`pyproject.toml`.

# Deploy & device

This is a dev checkout; production runs on a remote RPi via `make deploy`, which
the user runs. The Fire TV is a grandmother's live TV — never disrupt active
playback; if you must interact, restore her prior state afterward.

# Commits

Small, atomic, single-purpose commits, and only when asked. Don't stage
untracked files you didn't create. Content/curation messages in pt-BR, code in
English.

# config.toml

Keep comments to bare title labels (e.g. `# TV Aparecida`) — no explanatory
prose, no cron-schedule docs. The b6 rotation is movies only (a series
autoplays into uncurated episodes); confirm a Netflix title is a film, and
verify its ID, before adding.
