# Repository safety

This is a personal dotfiles repository. Keep it free of secrets, sensitive values,
and workplace-specific details, including in examples, comments, documentation,
tests, and agent configuration.

- Never add credentials, API tokens, passwords, private keys, session cookies,
  connection strings containing credentials, or other sensitive values.
- Never add employer or client names, internal domains or URLs, private repository
  references, project names, ticket identifiers, account identifiers, customer
  data, or proprietary workflows and configuration.
- Use generic placeholders and synthetic examples. Keep real private settings
  outside this repository, such as in `~/.zshrc.local`, and reference them through
  environment variables or external local configuration.
- Ignoring a file does not protect data already tracked by Git. Do not rely on
  `.gitignore` alone to keep sensitive information out of the repository.

## Routine safety check

For every task that changes repository files, run this check before declaring
completion, and before any explicitly authorized commit or push:

1. Review the full working-tree diff, including staged changes and new files, for
   secrets, sensitive values, and workplace-specific details.
2. Scan all tracked files and new files intended for inclusion, including hidden
   configuration, for credential patterns and workplace-specific references.
   Use an available secret scanner such as Gitleaks, plus targeted searches and
   manual review for workplace details that secret scanners do not detect. If no
   scanner is available, use pattern searches and manual review, and disclose
   that limitation. Do not treat a clean automated scan as proof of safety.
3. Remove or replace findings introduced by the task and repeat the check. Report
   pre-existing findings without altering unrelated files. If a real credential
   may already have been committed, flag the need for revocation or rotation;
   deleting its current value does not remove it from Git history.
4. Report what was checked and any unresolved findings or coverage limitations.
   Identify findings by path and line number, never by reproducing sensitive
   values in output, logs, or the completion summary.
