export EDITOR='nvim'
export PAGER="delta"
export GIT_PAGER="delta"
export LG_CONFIG_FILE="$HOME/.config/lazygit/config.yml"

# === pi ===
pi() {
  local node_version
  local node_dir
  local pi_executable
  local PI_DEFAULT_MODEL="${PI_DEFAULT_MODEL:-}"
  local ASDF_NODEJS_VERSION

  [[ -f "$HOME/.pi/.local.env" ]] && source "$HOME/.pi/.local.env"

  if [[ ! -r "$HOME/.tool-versions" ]]; then
    printf 'No readable ~/.tool-versions file was found.\n' >&2
    return 1
  fi

  node_version=$(awk '$1 == "nodejs" { print $2; exit }' "$HOME/.tool-versions")
  if [[ -z "$node_version" ]]; then
    printf 'No nodejs version is configured in ~/.tool-versions.\n' >&2
    return 1
  fi

  node_dir=$(asdf where nodejs "$node_version") || return
  pi_executable="$node_dir/bin/pi"
  if [[ ! -x "$pi_executable" ]]; then
    printf 'Pi is not installed for Node.js %s.\n' "$node_version" >&2
    return 1
  fi

  if [[ -n "$PI_DEFAULT_MODEL" ]]; then
    env -u ASDF_NODEJS_VERSION \
      "$node_dir/bin/node" "$pi_executable" \
      --model "$PI_DEFAULT_MODEL" "$@"
  else
    env -u ASDF_NODEJS_VERSION \
      "$node_dir/bin/node" "$pi_executable" "$@"
  fi
}

# === Java + Android ===
export JAVA_HOME=$(asdf where java)
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin"
