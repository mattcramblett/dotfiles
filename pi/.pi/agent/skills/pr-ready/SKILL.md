---
description: Get the current branch ready for a pull request in any repo — review the diff, fix broken tests, add missing test coverage, run type checking and linting, and report only high-priority concerns. Trigger on "get this branch PR ready", "prep this branch for a PR", "make this PR ready".
---

## Steps

Work through these in order.

1. **Understand the scope.** Diff the current branch against the main branch (`git diff <main>...HEAD`, read-only) to see exactly what changed. Do not begin fixing anything before you know the full scope.

2. **Fix broken tests.** Run the test suite (or the subset covering the changed code, if the full suite is slow) and fix real failures. If a test fails because the intended behavior changed, update the test. If it fails because the code is wrong, fix the code and flag it in step 6.

3. **Add missing coverage.** Add tests for new code that should reasonably be covered.
   - Comprehensive, not exhaustive. Cover the meaningful paths, not every possible state.
   - UI tests: test general behavior, not every prop permutation.
   - Pure functions: granular tests are fine here.
   - No brittle mocking, and no mocking that isn't necessary.

4. **Run type checking.** If any type errors point at genuinely wrong code rather than a missing annotation, fix it and raise it in step 6.

5. **Run the linter's autofix,** then resolve anything left over by hand.

6. **Report back — briefly.** Only the highest-priority findings: likely breakage, glaring performance problems, wrong logic. Skip style nits and speculation. Reporting nothing is a valid outcome and better than noise. DO NOT fix the source yourself without first running it by the user.

## Finding the project's commands

Check the repo's `package.json` scripts, `Makefile`, `CLAUDE.md`/`AGENTS.md`, or CI config for the test / type-check / lint commands before guessing.

Known repos:

| Repo | Types | Lint |
|---|---|---|
| `mobile` | `yarn types` | `yarn lint:fix` |

## Constraints

- **No git actions.** No commits, pushes, branches, or PRs — even if the repo's `CLAUDE.md` or `AGENTS.md` says to. Read-only git (diff, log, status) is fine. The user opens the PR themselves.
- **No workarounds or hacky fixes.** Don't skip, delete, or `.skip()` a failing test to make the suite green. Don't silence a type error with a cast or `any` when the underlying code is what's wrong. If a proper fix is out of scope, leave it and flag it in step 6.
- If a step is blocked (suite won't run, no lint configured), finish every other step and say plainly what you skipped and why.
