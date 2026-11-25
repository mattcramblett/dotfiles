# Dotfiles

Personal macOS development environment managed with [GNU Stow](https://www.gnu.org/software/stow/) and Homebrew.

## Included configuration

- **Neovim**: editor, LSP, formatting, linting, and plugins
- **tmux**: terminal sessions, navigation, theme, and Pi agent picker
- **Pi**: coding agent settings, extensions, prompts, skills, and themes
- **Ghostty**: terminal configuration
- **lazygit**: terminal Git interface
- **Zsh**: shell environment, aliases, completions, and tool setup
- **Ruby tools**: Ruby LSP, Sorbet, and Tmuxinator managed through Bundler
- **bin**: personal command-line tools

Each top-level package mirrors its destination under the home directory. Stow creates the required symlinks without copying the files.

## Setup

Clone the repository:

```bash
git clone git@github.com:mattcramblett/dotfiles.git ~/dotfiles
cd ~/dotfiles
```

Run the installer:

```bash
./install.sh
```

The script installs Homebrew dependencies, configures Java, Node.js, and Ruby through asdf, creates `~/.tool-versions` when it does not already exist, installs Rust tools, and links the dotfiles into the home directory with Stow.

Existing files at the target paths may need to be moved before running the installer.

## Updating links

After adding or moving files within a package, restow it:

```bash
stow --restow --target="$HOME" <package>
```

To remove a package's links:

```bash
stow --delete --target="$HOME" <package>
```

## Custom scripts

### `wt`

From inside tmux, open a local or remote branch in a sibling Git worktree, or create a new branch from the latest `origin/main` or `origin/master`, then switch to a named tmux session:

```bash
wt <worktree-name>
```

For example, `wt feature/login` creates the branch `feature/login`, places the worktree beside the primary repository, and names the tmux session `<repository>-feature-login`. The `mattcramblett/` branch prefix is omitted from local directory and tmux session names, while the full Git branch name is preserved. Override the prefix with the `worktree.branchPrefix` Git configuration value. Dots and colons in session names become underscores.

`wt` waits for `wt-setup` to finish before creating the session or moving an agent pane. Setup installs asdf runtimes and locked Ruby and Node dependencies. Failures preserve the worktree, leave the agent in its original session, and print a retry command.

#### Dependency setup

`wt-setup` discovers tracked dependency roots from a manifest and matching lockfile, including independent projects in subdirectories. Workspace packages without their own lockfiles are installed by their parent project, not separately. Repositories without recognized dependency roots still get runtime setup. Setup is serialized per repository to avoid competing installs from concurrent worktree creation.

- **Ruby**: selects the `BUNDLED WITH` version from `Gemfile.lock`, installing that Bundler version if needed. Runs a frozen `bundle check`, then a frozen `bundle install` only when necessary. Verifies the locked bundle can activate with `bundle exec ruby -e exit` before reporting success. Existing gems are reused through Bundler's configured gem store, and automatic gem cleanup is disabled to preserve versions needed by other worktrees. Conflicting local frozen/cleanup settings stop setup without changing configuration. Checkout-local bundle paths are respected but not copied.
- **Node**: detects Yarn, npm, or pnpm from `packageManager` and lockfiles. Uses Corepack for Yarn/pnpm when available and verifies declared package-manager versions. Runs Yarn's immutable/frozen install, `npm ci`, or `pnpm install --frozen-lockfile`. Conflicting lockfiles require an explicit `packageManager`.
- **Runtimes**: runs `asdf install` for the root and applicable nested `.tool-versions` files. Exact `.ruby-version`, `.node-version`, and `.nvmrc` versions are supported when the tool is not declared in `.tool-versions`.

For compatible Yarn 2+ `node-modules` installs on macOS, setup seeds missing root and workspace dependency directories from the primary checkout with `cp -cR -P`. APFS uses copy-on-write, so writes remain independent. Inputs and Node runtime identities must match; external dependency links prevent reuse. Internal workspace links are relocated into the new worktree. Yarn's dependency-location metadata is included, but its build-state cache is not, so install scripts are evaluated in the new checkout. Yarn always runs afterward, even when seeding succeeds. With Yarn 4+, packages containing environment or authentication files are omitted from the copy and restored normally by Yarn, so their local configuration is never copied from the source. Older Yarn versions and unsupported state formats fall back to a normal install when exclusions are needed. npm and pnpm use their native caches instead; npm's clean install would discard seeded directories.

Only dependency directories are seeded, never checkout-level environment files or `.bundle/config`. No databases, migrations, service startup, or arbitrary repository bootstrap scripts run automatically. Package-manager lifecycle scripts run normally. Reuse is best effort; unavailable or incompatible source installs fall back to a normal install. On filesystems without cloning, macOS `cp` may use an independent regular copy.

To disable directory seeding for a new worktree:

```bash
wt --no-reuse feature/example
```

To retry setup without recreating a worktree or touching tmux:

```bash
wt-setup --path /path/to/worktree
wt-setup --path /path/to/worktree --no-reuse
```

Omit `--path` to use the current repository. `--source /path/to/checkout` chooses another checkout of the same repository for seeding. Existing target dependency directories are never overwritten by seeding, including on retries. Symlinked dependency directories are rejected before an installer runs, so a retry cannot modify another checkout through a shared link. `--no-reuse` disables directory seeding, not package-manager caches or Bundler's shared gem store; use it on a fresh worktree for an unseeded install. Setup does not update lockfiles or copy authentication configuration. Existing credentials must already be available to the package managers.

#### Local overrides

Optional configuration lives at `$(git rev-parse --path-format=absolute --git-common-dir)/worktree-setup.json`, outside tracked files and shared across the repository's worktrees. No configuration is needed for automatic detection. A `projects` array replaces discovery and runs in the listed order:

```json
{
  "projects": [
    {"path": ".", "type": "ruby"},
    {"path": "client", "type": "node"},
    {"path": "tools", "type": "command", "command": ["./bootstrap", "--local"]}
  ]
}
```

For Yarn 2+ monorepos, a Node project may specify `"workspaces": ["example-root", "example-app"]` to run an immutable `yarn workspaces focus` instead of installing every workspace. Include the root workspace when its tooling is needed. Workspace selection is explicit, never guessed from the current directory. Other package managers currently require a custom command for subset installs.

Use `{"projects": []}` to keep runtime setup but disable automatic dependency installs. Custom commands are argument arrays, not shell strings; they are explicitly trusted local setup and do not inherit the built-in adapters' lockfile guarantees. Paths must stay inside the worktree without traversing symlinks. Keep secrets out of this file, and do not put private repository settings in these dotfiles. The `ticket-work` skill relies on the same setup and does not reinstall dependencies immediately afterward.

For agents or when you want to stay in your current session:

```bash
wt --background mattcramblett/SERVEBX-100
```

This creates a detached session without switching or attaching any terminal, and works outside tmux too. It still waits for setup to finish and reports the worktree path and session name on success.

To move a running agent's pane into the new session:

```bash
wt --background --move-pane "$TMUX_PANE" mattcramblett/SERVEBX-100
```

Run this from the agent's command tool, not from a different pane. The first window has Neovim across the top (60% height), with lazygit on the bottom left and the existing agent on the bottom right. The agent gets 60% of the bottom row's width. The process and conversation stay alive; no resume command or second agent is needed. Your terminal stays on its current session. Other panes are untouched, and a replacement shell window is created if moving the pane would otherwise destroy the original session.

Neovim, lazygit, and new windows start in the worktree. With the updated tmux configuration, new splits also use the worktree even when split from the moved agent. Moving a process cannot change its working directory, so the agent must use explicit worktree working directories and absolute file paths. Reload existing tmux servers with `tmux source-file ~/.config/tmux/tmux.conf` to activate the new window and split bindings.

The `ticket-work` skill moves its coordinating pane into the first new worktree session, then names that session after the ticket and task. It does not rename your main session or move the pane again for additional PRs. Outside tmux, it uses plain `--background` instead.

`wt` automatically registers the repository for `wta`, even if later setup fails. Registry errors are reported without interrupting worktree creation.

Run the command tests with `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests` and the Pi extension tests with `node --test tests/tmux_status.test.mjs` (Node.js 22.18+). The layout tests use separate tmux servers and stub editor and agent processes, without touching your sessions or contacting an agent provider.

### `wta`

Find a worktree across registered repositories and attach to its tmux workspace:

```bash
wta                              # Open the searchable picker
wta SERVEBX-100                   # Start with a ticket, task, branch, or repo search
wta --path /path/to/worktree      # Attach directly, without fzf
wta --path /path/to/worktree --agent pi
wta --fresh                       # Recreate a workspace with a new conversation
wta --list                       # JSON output for scripts
```

Register each existing repository once, from any directory. All its current worktrees appear in the picker, including the primary checkout. Future worktrees created with `wt` register automatically. There is no home-directory or code-directory scan.

```bash
wta --register /path/to/repository
```

The picker shows only three columns: repository, task/branch, and tmux status (`running` or `stopped`). The task label is the tmux session name, falling back to the branch. Filtering searches these visible columns. The preview shows the full branch, path, last-recorded agent, and Git status. Repositories are sorted reverse alphabetically, with running workspaces first and then recently used worktrees within each repository. `prefix+t` opens this same picker from any directory, not just a Git checkout. Press Enter to attach or Esc to cancel selection.

The picker matches the navy, blue, and green tmux palette, with bold repository names, colored running/stopped status dots, and a highlighted selection. `Ctrl-N` and `Ctrl-P` wrap through the list. `Ctrl-/` toggles the details preview, which moves below the list in narrow terminals. The footer shows the available keys. Icons use ordinary Unicode characters and do not require a patched font.

Press `Ctrl-X` to remove the selected linked worktree. Confirmation lists its branch, path, and every tmux session explicitly tagged with that exact worktree path, including renamed sessions and sessions containing agents whose working directory stayed elsewhere. Closing a session closes all of its panes and their attached commands. Removal never uses force: the primary worktree and worktrees with uncommitted changes, untracked files, or a lock are protected. All files inside the worktree, including ignored files, are deleted. The Git branch and conversation files stored outside that worktree are preserved.

Only after Git successfully removes the worktree are the confirmed tagged sessions closed and its workspace metadata discarded. Unrelated and untagged sessions are left alone, even if their names or pane directories look similar. Attached clients switch to another session outside the deleted tree first, or a new home-directory shell session if none exists. The picker refreshes with the current query and displays the removal status without invoking agent resumption. Deleting the session that launched the picker may close it too; `prefix+t` can reopen it from the remaining session. If session identity changes during confirmation, removal is refused; if tmux cleanup fails after Git removal, the error explicitly reports that the worktree is already gone.

Selection reuses a running session at that worktree, leaving its panes and processes untouched. Otherwise, it recreates the Neovim/lazygit/agent layout described above, focused on the agent pane. It switches sessions inside tmux and attaches outside tmux. It does not create branches or worktrees, fetch, or run setup again. An unrelated session with the same name is never taken over.

The managed `pi` shell wrapper remembers the last agent invoked in a worktree, and Pi's tmux status extension records its exact conversation file, ID, and working directory. When recreating a workspace, `wta` resumes that conversation with `pi --session <file>`. An optional `claude` wrapper and existing `agent-status` hooks capture Claude's transcript path and conversation ID for `claude --resume <id>`; Claude is not required or installed by this repository.

Use `wta --fresh` to start a new conversation instead. Missing, invalid, or deleted conversation references fall back to a normal agent launch, as does a native resume command that exits with an error. Interrupting a resume does not start another conversation. Existing running tmux workspaces are never restarted, even with `--fresh`.

If no agent is known or its command is unavailable, the pane opens a shell. Exiting an agent also leaves a shell. `--agent` remembers an override; it never replaces a running process in an existing workspace. Switching to a different agent clears the old agent's conversation reference. Agent names must be simple commands such as `pi` or `claude`, not paths or commands with arguments.

Other agents can use the shared registration command, including from their launch wrapper:

```bash
wt-workspace remember-agent some-agent
wt-workspace remember-agent some-agent --path /path/to/worktree
```

Worktree-tagged tmux sessions take precedence over an agent's original directory, so the agent moved by `/ticket-work` is tracked correctly. Task-session renames are remembered through a tmux hook and reconciled when listing/attaching. Metadata lives under `${XDG_STATE_HOME:-$HOME/.local/state}/worktrees/`, outside this repository. Git remains authoritative for current worktrees. Missing/deleted worktrees are skipped, and registry failures do not block direct attachment.

Conversation references move with the pane when `/ticket-work` moves it. A reference belongs to one worktree at a time, so returning to the original checkout does not launch a duplicate of the moved conversation. The editor, lazygit, and recovery shell stay rooted in the worktree; a resumed agent uses its recorded working directory so its project lookup and internal tool paths remain consistent with the original conversation. Registry metadata contains only references, not a copy of conversation history. Recreating a workspace after reboot does not restore live processes or in-flight agent work.

Existing sessions without conversation metadata start normally rather than guessing the most recent conversation. Run `/reload` once in already-open Pi sessions to load the updated extension before closing them. Pi session changes, including new, resumed, forked, and ephemeral sessions, update or clear the stored reference. Non-interactive Pi workers do not publish conversation references. Other agents still launch normally unless they have an explicit resume integration.

Claude capture requires its `SessionStart` hook to invoke `agent-status set claude idle`; the same script can also capture from `UserPromptSubmit`, `Stop`, and `StopFailure` hooks. This repository does not change external Claude settings. For scripted capture, see `wt-workspace remember-conversation --help`. A plain `remember-agent` call marks a new launch and clears its previous conversation reference.

Python 3 must be available through your asdf setup; it is not installed through Homebrew. Link the commands and shared library, load the wrappers in new shells, and reload the tmux hook and bindings:

```bash
stow --restow --target="$HOME" bin zsh tmux
exec zsh
# Run inside tmux:
tmux source-file ~/.config/tmux/tmux.conf
```

The commands require Python 3 and Git. Attachment and removal require tmux; creating the layout also requires Neovim, lazygit, and Zsh. Only the interactive picker requires fzf. Shell startup customizations should preserve the managed wrappers if automatic tracking is desired.

### `wtlist`

Browse the current repository's worktrees and open the selected worktree in tmux:

```bash
wtlist
```

When run outside tmux, the selected worktree path is printed to standard output. This remains a current-repository picker; `prefix+t` and `wta` browse all registered repositories. `Ctrl-X` uses the shared `wtrm --path <worktree-path>` removal flow described above, including confirmation and cleanup of explicitly tagged tmux sessions. Direct removal requires a controlling terminal for confirmation.

## Features

### Zsh

The installer clones Oh My Zsh, Powerlevel10k, zsh-autosuggestions, and zsh-syntax-highlighting, installs the Meslo Nerd Font, and links the managed shell configuration. Powerlevel10k settings live in `zsh/.p10k.zsh`. Machine-specific or sensitive settings belong in the untracked `~/.zshrc.local` file.

The `pi` shell wrapper runs Pi with the Node.js version from `~/.tool-versions` without overriding the Node.js version selected by the current repository.

### Pi agent picker

Inside tmux, press `Ctrl-Space`, then `a`, to view running Pi agents, inspect their pane output, and jump to a selected agent. Press `Ctrl-R` in the picker to refresh the agent list and preview.

Press `Ctrl-Space`, then `t`, to browse worktrees across all registered repositories. Enter reuses or recreates the selected worktree's workspace; `Ctrl-X` confirms removal of the worktree and its explicitly tagged tmux sessions.
