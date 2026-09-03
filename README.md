# Dotfiles

Personal macOS development environment managed with [GNU Stow](https://www.gnu.org/software/stow/) and Homebrew.

## Included configuration

- **Neovim**: editor, LSP, formatting, linting, and plugins
- **tmux**: terminal sessions, navigation, theme, and Pi agent picker
- **Pi**: coding agent settings, extensions, prompts, skills, and themes
- **Ghostty**: terminal configuration
- **lazygit**: terminal Git interface
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

The script installs Homebrew dependencies, configures the latest Node.js and Ruby versions through asdf, installs Rust tools, and links the dotfiles into the home directory with Stow.

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

Create a sibling Git worktree from the latest `origin/main` or `origin/master` and open it in a new tmux window:

```bash
wt <worktree-name>
```

For example, `wt feature/login` creates the branch `feature/login`, places the worktree beside the primary repository, and names the tmux window `<repository>-feature-login`.

### `wtlist`

Browse the current repository's worktrees and open the selected worktree in tmux:

```bash
wtlist
```

When run outside tmux, the selected worktree path is printed to standard output. Press `Ctrl-X` in the picker to confirm and remove a linked worktree. The primary worktree cannot be removed, dirty worktrees are rejected by Git, and the branch is preserved.

## Features

### Pi agent picker

Inside tmux, press `Ctrl-Space`, then `a`, to view running Pi agents, inspect their pane output, and jump to a selected agent. Press `Ctrl-R` in the picker to refresh the agent list and preview.

Press `Ctrl-Space`, then `t`, to browse worktrees for the repository in the current pane. Selecting a worktree focuses an existing pane at that path or opens it in a new tmux window.
