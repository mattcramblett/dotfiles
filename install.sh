#!/usr/bin/env bash

set -euo pipefail

DOTFILES_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly DOTFILES_DIR

load_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    eval "$(brew shellenv)"
  elif [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    if [[ -x /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    else
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
}

add_asdf_plugin() {
  local name=$1
  local repository=$2

  if ! asdf plugin list | grep -qx "$name"; then
    asdf plugin add "$name" "$repository"
  fi
}

install_asdf_tool() {
  local name=$1
  local version

  version=$(asdf latest "$name")
  asdf install "$name" "$version"
  asdf set -u "$name" "$version"
}

load_homebrew
brew bundle --file="$DOTFILES_DIR/Brewfile"

stow \
  --dir="$DOTFILES_DIR" \
  --target="$HOME" \
  --restow \
  bin ghostty lazygit nvim pi tmux zsh

export ASDF_DATA_DIR="${ASDF_DATA_DIR:-$HOME/.asdf}"
export PATH="$ASDF_DATA_DIR/shims:$PATH"

add_asdf_plugin nodejs https://github.com/asdf-vm/asdf-nodejs.git
add_asdf_plugin ruby https://github.com/asdf-vm/asdf-ruby.git
install_asdf_tool nodejs
install_asdf_tool ruby

if ! command -v rustup >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs | sh -s -- -y
fi

if [[ -f "$HOME/.cargo/env" ]]; then
  # shellcheck source=/dev/null
  source "$HOME/.cargo/env"
else
  export PATH="$HOME/.cargo/bin:$PATH"
fi

rustup default stable
npm install --global @earendil-works/pi-coding-agent
cargo install cargo-generate cargo-udeps
