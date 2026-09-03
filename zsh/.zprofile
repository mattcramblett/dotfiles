if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

export ASDF_DATA_DIR="${ASDF_DATA_DIR:-$HOME/.asdf}"
path=(
  "$HOME/.local/bin"
  "$ASDF_DATA_DIR/shims"
  "$HOME/.cargo/bin"
  $path
)
typeset -U path
