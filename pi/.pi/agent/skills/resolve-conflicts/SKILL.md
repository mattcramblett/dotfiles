---
description: Resolve active merge conflicts, most often mid-rebase, by editing conflicted files to reflect the real intent of both sides, staging them, and continuing the rebase through to completion, without ever running `git commit` yourself or pushing. Once the rebase finishes cleanly, report a compact TL;DR on overlap with the PR's scope, breakage risk, and whether anything merged in undermines the branch's design. Trigger on "resolve conflicts", "fix merge conflicts", "rebase conflicts", "help me finish this rebase".
---

## Scope

- Handle only active conflicts (conflict markers in the working tree), most often mid-rebase, sometimes mid-merge.
- Resolve each conflicted file, stage exactly the files you resolved, then drive the rebase forward with `git rebase --continue` (or `git merge --continue`), repeating for each conflict until the whole rebase completes.
- **Never run `git commit` yourself, and never push (especially never force push).** `rebase --continue`'s implicit re-commit of already-existing commits is fine, that's just replaying history, not you authoring a new commit. The end goal is a fully rebased, clean working tree the user reviews, then commits/force-pushes themselves.
- Never `git rebase --skip` or `git rebase --abort` without asking first, those discard work.
- No broad `git add -A` / `git add .`, stage exactly the files you resolved.

## Steps

1. **On your first pass, before resolving anything, capture rebase context** so it's still available once the rebase directory disappears at completion:
   - `git rev-parse ORIG_HEAD` (pre-rebase branch tip)
   - `cat .git/rebase-merge/onto` (interactive rebase) or `.git/rebase-apply/onto` (apply-based)
   Keep both values for the end-of-rebase report.

2. **Find the conflicted files.** `git status` (or `git diff --name-only --diff-filter=U`).

3. **Resolve each file on its merits.** Read both sides of every conflict along with surrounding context (and the commit message being replayed, from `git status` or `.git/rebase-merge/message`). Reconcile what each side was actually trying to do, don't default to picking "ours" or "theirs" just to make the markers disappear. Remove all conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

4. **Stage only the resolved files.** `git add <file>` per file.

5. **Continue the rebase.** Run `GIT_EDITOR=true git rebase --continue` (the `GIT_EDITOR=true` avoids getting stuck if git wants to open an editor for a commit message; it accepts the default).
   - If this surfaces a new conflict, go back to step 2 for the new set of files.
   - If it completes with no more conflicts, the rebase is done, go to the end-of-rebase report.
   - If it fails for any reason other than a conflict (e.g. an error you don't recognize), stop and show the user the exact output rather than guessing.

## End-of-rebase report

Once `git rebase --continue` finishes the rebase (working tree clean, no rebase directory left), tell the user the rebase is complete and ready for their review, then produce this report using the `ORIG_HEAD` and `onto` values captured in step 1:

- Old base: `git merge-base <orig-head> <onto>`
- What merged into the base while this branch existed: `git log --oneline <old-base>..<onto>` and `git diff <old-base>..<onto>`
- The PR's own changes: `git diff <old-base>..<orig-head>`

Compare the two diffs (files touched, functions/signatures changed, patterns replaced) to answer:

1. **Fundamental change overlapping this PR's scope?** Did the base pick up changes touching the same files/behavior this branch is changing (not just adjacent code)?
2. **Breakage risk / needs manual testing?** Did any conflict resolution require real reconciliation (not just line-offset noise), or did an API/signature/behavior this branch depends on change?
3. **Undermines this branch's design choices?** Did the base rewrite, deprecate, or take a different architectural approach in the same area this branch is building on?

Report format, compact:

```
TL;DR
1. Overlapping scope: Yes/No, <one line why>
2. Breakage risk / manual test needed: Yes/No, <one line why>
3. Undermines design: Yes/No, <one line why>
```
