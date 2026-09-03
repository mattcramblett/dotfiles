ZSH_CONFIG_DIR="$HOME/.config/zsh"

source "$ZSH_CONFIG_DIR/aliases.zsh"
source "$ZSH_CONFIG_DIR/completions.zsh"
source "$ZSH_CONFIG_DIR/tools.zsh"

[[ -f "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"
