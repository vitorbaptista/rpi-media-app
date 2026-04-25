# Workflow

After non-trivial changes, run a review-fix loop with the `code-reviewer`
subagent until it returns clean:

1. Spawn `code-reviewer` on the changed files.
2. Apply the fixes that are real (skip nits unless they hide a bug).
3. Re-spawn `code-reviewer`, telling it which prior issues are already
   addressed so it doesn't re-flag them.
4. Stop when the reviewer says clean.
