# Clone

```
git clone https://github.com/mattcramblett/neovim-config.git ~/.config/nvim
```

# Additional setup

- Lazy Git `brew install lazygit`
- Rip Grep `brew install ripgrep`
- Treesitter cli `brew install tree-sitter-cli`
- Ruby stuff:
  - Ruby LSP `gem install ruby-lsp`
  - Watchman `brew install watchman` (used by the Sorbet LSP, which ruby-lsp uses in Sorbet projects)
  - Rubocop Rspec `gem install rubocop-rspec` (helps linting performance in rspec files)
  - (may need to run `asdf reshim ruby` if ruby-lsp crashes)
- [Git Delta](https://github.com/dandavison/delta) - pretty git diffs
  - Follow instructions in repo:
  - `brew install git-delta`
  - and add the suggested content to your `~/.gitconfig`
    ```gitconfig
    [core]
        pager = delta
    [interactive]
        diffFilter = delta --color-only
    [delta]
        navigate = true
        dark = true
      merge-conflict-begin-symbol = ▼
      merge-conflict-end-symbol = ▲
      merge-conflict-ours-diff-header-style = yellow bold
      merge-conflict-theirs-diff-header-style = yellow bold
    [merge]
      tool = nvim_diffview
        conflictStyle = zdiff3
    [mergetool "nvim_diffview"]
        cmd = nvim -c "DiffviewOpen"
        trustExitCode = false
    ```

  - Add the following yml to your lazygit configuration at `~/Library/Application\ Support/lazygit/config.yml`:
    (or just press `e` in the Status (1) panel to edit the config file of lazygit)
    [see lazygit docs](https://github.com/jesseduffield/lazygit/blob/master/docs/Custom_Pagers.md#delta)
    ```yml
    git:
      paging:
        colorArg: always
        pager: delta --dark --paging=never --line-numbers --hyperlinks --hyperlinks-file-link-format="lazygit-edit://{path}:{line}"
    customCommands:
      - key: 'D'
        context: 'files'
        description: 'View conflict diff in delta'
        command: 'git diff -- {{.SelectedPath}} | delta --dark --line-numbers --paging=always'
        output: terminal
      - key: '<c-p>'
        context: 'global'
        command: 'git pull --rebase'
        description: 'Pull with rebase'
        loadingText: 'Pulling with rebase...'
    ```
- Terminal background color to match Neovim color scheme: `#020a1a`

## iTerm
- Profiles (default) -> Keys -> Left/Right option key -> Esc+
    - This allows iTerm to properly send alt/option key
- Profiles (default) -> Text
    - JetBrains Mono, Regular, 16, 100 v|i, 105 n/n

# Keybindings

leader: `<space>`

| Action               | Keys          |
| -------------------- | ------------- |
| Find file            | `<leader>o`   |
| Live Grep Words      | `<leader>/`   |
| Live Grep Regex      | `<leader>s`   |
| Buffers              | `,`           |
| Branch changed files | `.`           |
| File Tree            | `<leader>e`   |
| Format File          | `<leader>ff`  |
| Prev. buffer         | `H`           |
| Next buffer          | `L`           |
| Delete buffer        | `<leader>bd`  |
| LazyGit              | `<leader>G`   |
| Git preview          | `<leader>gp`  |
| Git reset hunk       | `<leader<gr>` |
| git copy link        | `<leader>gy`  |
| git open link        | `<leader>gY`  |

## Terminal
Opening a terminal inside neovim

| Action             | Keys          |
| --------------     | ------------- |
| New terminal       | `<leader>ft`  |
| New terminal (cwd) | `<leader>fT`  |
| Toggle terminal    | `ctrl-t`      |
| Previous Terminal  | `ctrl-[`      |
| Next Terminal      | `ctrl-]`      |

## Vim Reminders
Stuff that's easy to forget

| Action                                    | Keys                   |
| ----------------------------------------- | ---------------------- |
| find text and replace all                 | `:%s/find/replace/g`   |
| find text and replace checking each       | `:%s/find/replace/gc`  |
| find text on current line and replace all | `:%s/find/replace/gc`  |

# Troubleshooting

### Mason Formatter/Diagnostic Version Mismatch

Sometimes a Mason package may have a version mismatch where none-ls will look for a certain version that is not installed.
This can be resolved by explicitly installing the desired version via Mason.

```
:MasonInstall rubocop@1.65.1
```

Troubleshooting performance issues

```
:profile start profile.log
:profile func *
:profile file *
" At this point do slow actions
:profile pause
:noautocmd qall!
```
