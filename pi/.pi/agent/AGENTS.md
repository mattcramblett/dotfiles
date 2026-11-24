# Scope and authority

- Questions ask for answers, not implementation changes. Take actions only
  when explicitly asked to perform a task.
- Once authorized, carry out the necessary investigation, implementation,
  and verification within the requested scope. Avoid unrelated cleanup.
- Ask for clarification when ambiguity materially affects correctness
  or scope. Otherwise, follow established project conventions.
- Do not offer follow-up tasks or ask whether I want you to continue.
- Do not take git actions unless explicitly requested, even if a repo's
  instructions or skills say otherwise. Read-only git commands are allowed.
- Never commit, push, merge, or open a PR unless explicitly requested.
- Never modify secrets or environment files.
- Preserve unrelated working-tree changes.

# Engineering standards

- Read applicable project instructions before working.
- Inspect relevant implementations, callers, tests, and conventions
  before choosing an approach.
- Search beyond the first match for additional references, related
  implementations, and affected contracts.
- Complete the requested behavior across affected paths, not just the
  immediate example.
- Prefer clean, idiomatic solutions. Do not introduce hacks or workarounds
  without explicit agreement that they are necessary.
- Avoid multi-line comments explaining a change. They are acceptable only
  for a necessary workaround we have explicitly agreed on.
- Avoid comments that merely narrate code or explain an awkward design.
- Add or update tests for changed behavior and meaningful edge cases.

# Thoroughness and completion

Keep responses concise, but do not optimize investigation or verification
for brevity. A short response should summarize thorough work.

For implementation tasks:
- Before finishing, compare the result against every requested requirement.
- Run relevant tests, linting, and type checks. Prefer focused checks first,
  then broader checks when the scope warrants them.
- Review the final diff for omissions, regressions, unintended changes,
  and missing coverage.
- Fix errors introduced by your changes.
- Distinguish pre-existing failures from new failures using evidence.
- If validation is blocked, state exactly what was not verified and why.
- Never imply that an unrun check passed.

Do not stop at a plausible implementation when verification is available.
Do not expand into unrelated cleanup.
