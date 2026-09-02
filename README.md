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

## Features

### Pi agent picker

Inside tmux, press `Ctrl-Space`, then `a`, to view running Pi agents, inspect their pane output, and jump to a selected agent. Press `Ctrl-R` in the picker to refresh the agent list and preview.
