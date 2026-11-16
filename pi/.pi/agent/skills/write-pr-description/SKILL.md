---
name: write-pr-description
description: Write or rewrite a pull request description in plain English, leading with what changes and why, followed only by critical reviewer context. Use when asked to write, draft, summarize, or improve a PR description or pull request body.
---

# Write a PR description

Write for a capable coworker who has not followed the work. Give them enough context to make sense of the PR without making them reconstruct its purpose from the code or read a change inventory.

## Understand the change

1. Read the user's request, supplied notes, and applicable project instructions. If rewriting an existing description, preserve its confirmed intent and essential context.
2. When working from a branch, identify the intended base from repository or PR context. Inspect the full branch diff against its merge base, not just the latest commit. Use read-only git commands. Do not assume the base is named `main`; ask if the target is materially ambiguous. Keep uncommitted changes separate from what is actually on the branch unless the user includes them in scope.
3. Read relevant code, tests, and surrounding behavior to understand the outcome and significant implications. Commit messages and file lists are clues, not substitutes for understanding the change. When showing a git diff, use `git diff --no-color <base>...HEAD | delta --paging=never --line-numbers`.
4. Identify what changes, why it matters, and anything a reviewer needs to know that the code alone will not explain. Use supplied notes when code cannot establish the motivation. Ask only when missing context prevents an accurate description; do not invent intent, benefits, risks, links, or test results.

Investigate enough to be accurate, but do not turn a writing task into a code review, implementation task, or test run. If only notes or a diff are available, write from that evidence and keep material uncertainties outside the draft.

## Writing rules

- Use plain, conversational English, like talking to a coworker. Avoid jargon, unexplained acronyms, terse shorthand, corporate language, verbose explanations, and em dashes. Be concise without becoming cryptic.
- Lead with the bottom line: one or two sentences explaining what is changing at the concept or behavior level, followed by a brief statement of why. Do not open with background, a file name, a class name, or an implementation walkthrough.
- Describe the actual outcome. For internal changes, explain their effect on the system or development work rather than inventing a user-facing benefit.
- Follow with `Details` only when there is important additional context. Include critical reviewer callouts, not an exhaustive list of changes. Omit the section when the opening is enough.
- Include a detail only if it helps the reviewer understand intent, assess a meaningful tradeoff, or avoid a significant mistake. Examples include a non-obvious constraint, a deliberate limitation, a compatibility risk, or required rollout sequencing. These are possibilities, not a checklist to fill.
- Leave out what is readily visible in the code: file inventories, method-by-method explanations, routine wiring, obvious test additions, and mechanical changes. A large diff does not require a long description.
- Use code references only when necessary to point out something specific. Explain the concept first and name only the file, symbol, or location the reviewer actually needs.
- Do not repeat the summary in Details. Prefer a few short sentences or bullets over nested sections. Each point must earn the reader's attention.
- Include testing information only when requested, required by the repository's PR template, or important to review confidence. Report only observed results and clearly distinguish checks not run. Do not add generic testing, rollout, or risk sections by default.
- Respect required repository templates, but keep their content selective and preserve the what-then-why opening wherever possible. Do not manufacture content to fill optional sections.

## Default shape

```markdown
## Summary
[One or two sentences explaining what changes, focused on behavior or concept.]

[Briefly explain why the change is needed.]

## Details
- [Critical reviewer context that is not obvious from the code.]
```

Remove placeholders. Omit Details when it adds nothing. Do not label the opening "BLUF" or add a title unless requested or required by the repository.

## Scope and delivery

- A request to write, draft, or rewrite a description produces text in the conversation. This skill alone does not authorize creating a PR, updating a remote description, editing repository files, or taking git actions beyond read-only inspection.
- Publish or update a PR only when explicitly requested. Confirm the target from context, preserve unrelated content, and verify the write before claiming success.
- Return the ready-to-paste description without a preamble explaining the writing process. Keep necessary questions or source-access limitations outside the draft.

## Final check

Read it as a reviewer seeing the work for the first time. Does the opening explain what changes and why? Does every later point provide necessary context rather than narrate the diff? Remove repetition, jargon, unnecessary code references, unsupported claims, and anything the reviewer can easily learn by reading the code. Keep enough context to understand the PR, not every detail of how it was built.
