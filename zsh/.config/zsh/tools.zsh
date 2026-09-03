export EDITOR='nvim'
export PAGER="delta"
export GIT_PAGER="delta"
export LG_CONFIG_FILE="$HOME/.config/lazygit/config.yml"

# === pi ===
# Load pi with local defaults:
[ -f ~/.pi/.local.env ] && source ~/.pi/.local.env

pi() {
 if [[ -n "$PI_DEFAULT_MODEL" ]]; then
   command pi --model "$PI_DEFAULT_MODEL" "$@"
 else
   command pi "$@"
 fi
}

# === Java + Android ===
export JAVA_HOME=$(asdf where java)
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin"
