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
  local version_prefix=${2:-}
  local version

  if [[ -n "$version_prefix" ]]; then
    version=$(asdf latest "$name" "$version_prefix")
  else
    version=$(asdf latest "$name")
  fi

  asdf install "$name" "$version"
  asdf set -u "$name" "$version"
}

clone_dependency() {
  local repository=$1
  local destination=$2

  if [[ -d "$destination/.git" ]]; then
    return 0
  fi

  if [[ -e "$destination" ]]; then
    printf 'Cannot install %s because the destination already exists.\n' "$destination" >&2
    exit 1
  fi

  git clone --depth=1 "$repository" "$destination"
}

load_homebrew
brew bundle --file="$DOTFILES_DIR/Brewfile"

clone_dependency https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
clone_dependency \
  https://github.com/romkatv/powerlevel10k.git \
  "$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
clone_dependency \
  https://github.com/zsh-users/zsh-autosuggestions.git \
  "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions"
clone_dependency \
  https://github.com/zsh-users/zsh-syntax-highlighting.git \
  "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting"

stow \
  --dir="$DOTFILES_DIR" \
  --target="$HOME" \
  --restow \
  bin ghostty lazygit nvim pi tmux zsh

export ASDF_DATA_DIR="${ASDF_DATA_DIR:-$HOME/.asdf}"
export PATH="$ASDF_DATA_DIR/shims:$PATH"

add_asdf_plugin java https://github.com/halcyon/asdf-java.git
add_asdf_plugin nodejs https://github.com/asdf-vm/asdf-nodejs.git
add_asdf_plugin ruby https://github.com/asdf-vm/asdf-ruby.git
install_asdf_tool java temurin-21
install_asdf_tool nodejs
install_asdf_tool ruby

BUNDLE_GEMFILE="$DOTFILES_DIR/Gemfile" bundle install
ruby_version=$(asdf current ruby | awk '$1 == "ruby" { print $2; exit }')
asdf reshim ruby "$ruby_version"

if [[ ! -x "$HOME/.cargo/bin/rustup" ]]; then
  curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs | \
    sh -s -- -y --no-modify-path
fi

export PATH="$HOME/.cargo/bin:$PATH"
rustup default stable
npm install --global @earendil-works/pi-coding-agent
cargo install cargo-generate cargo-udeps
