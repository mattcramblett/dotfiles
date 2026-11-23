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

If the worktree has a root `.tool-versions` file, `wt` waits for `asdf install` to succeed before creating the session. If installation fails, it exits with an error and preserves the worktree for recovery.

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

Run the command tests with `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests`. The layout tests use separate tmux servers and stub editor and agent processes, without touching your sessions.

### `wta`

Find a worktree across registered repositories and attach to its tmux workspace:

```bash
wta                              # Open the searchable picker
wta SERVEBX-100                   # Start with a ticket, task, branch, or repo search
wta --path /path/to/worktree      # Attach directly, without fzf
wta --path /path/to/worktree --agent pi
wta --list                       # JSON output for scripts
```

Register each existing repository once, from any directory. All its current worktrees appear in the picker, including the primary checkout. Future worktrees created with `wt` register automatically. There is no home-directory or code-directory scan.

```bash
wta --register /path/to/repository
```

The picker shows the repository, task/branch, last-used agent, running/stopped state, and path, with a Git status preview. Running workspaces appear first, then recently used worktrees. Cancel without changing anything.

Selection reuses a running session at that worktree, leaving its panes and processes untouched. Otherwise, it recreates the Neovim/lazygit/agent layout described above, focused on the agent pane. It switches sessions inside tmux and attaches outside tmux. It does not create branches or worktrees, fetch, or run setup again. An unrelated session with the same name is never taken over.

The managed `pi` shell wrapper remembers the last agent invoked in a worktree. An optional `claude` wrapper does the same on machines where Claude is installed; Claude is not required or installed by this repository. The agent starts normally, not with an automatic conversation-resume command. Use its own resume UI if desired. If no agent is known or its command is unavailable, the pane opens a shell. Exiting an agent also leaves a shell. `--agent` remembers an override; it never replaces a running process in an existing workspace. Agent names must be simple commands such as `pi` or `claude`, not paths or commands with arguments.

Other agents can use the shared registration command, including from their launch wrapper:

```bash
wt-workspace remember-agent some-agent
wt-workspace remember-agent some-agent --path /path/to/worktree
```

Worktree-tagged tmux sessions take precedence over an agent's original directory, so the agent moved by `/ticket-work` is tracked correctly. Task-session renames are remembered through a tmux hook and reconciled when listing/attaching. Metadata lives under `${XDG_STATE_HOME:-$HOME/.local/state}/worktrees/`, outside this repository. Git remains authoritative for current worktrees. Missing/deleted worktrees are skipped, and registry failures do not block direct attachment.

Existing sessions without metadata fall back to their session directory and a branch-derived name. Agents launched without the managed wrappers or registration command are not inferred. Conversation history and resume IDs are not recorded. This recreates a workspace after reboot, not live processes or in-flight agent work.

Python 3 must be available through your asdf setup; it is not installed through Homebrew. Link the commands and shared library, load the wrappers in new shells, and reload the tmux hook and bindings:

```bash
stow --restow --target="$HOME" bin zsh tmux
exec zsh
# Run inside tmux:
tmux source-file ~/.config/tmux/tmux.conf
```

The commands require Python 3 and Git. Attachment requires tmux; creating the layout also requires Neovim, lazygit, and Zsh. Only the interactive picker requires fzf. Shell startup customizations should preserve the managed wrappers if automatic tracking is desired.

### `wtlist`

Browse the current repository's worktrees and open the selected worktree in tmux:

```bash
wtlist
```

When run outside tmux, the selected worktree path is printed to standard output. Press `Ctrl-X` in the picker to confirm and remove a linked worktree. The primary worktree cannot be removed, dirty worktrees are rejected by Git, and the branch is preserved.

## Features

### Zsh

The installer clones Oh My Zsh, Powerlevel10k, zsh-autosuggestions, and zsh-syntax-highlighting, installs the Meslo Nerd Font, and links the managed shell configuration. Powerlevel10k settings live in `zsh/.p10k.zsh`. Machine-specific or sensitive settings belong in the untracked `~/.zshrc.local` file.

The `pi` shell wrapper runs Pi with the Node.js version from `~/.tool-versions` without overriding the Node.js version selected by the current repository.

### Pi agent picker

Inside tmux, press `Ctrl-Space`, then `a`, to view running Pi agents, inspect their pane output, and jump to a selected agent. Press `Ctrl-R` in the picker to refresh the agent list and preview.

Press `Ctrl-Space`, then `t`, to browse worktrees for the repository in the current pane. Selecting a worktree focuses an existing pane at that path or opens it in a new tmux window.
