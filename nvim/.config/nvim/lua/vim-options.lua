vim.g.mapleader = " "
vim.cmd("set expandtab")
vim.cmd("set tabstop=2")
vim.cmd("set softtabstop=2")
vim.cmd("set shiftwidth=2")

vim.opt.guicursor = "n-v-c:block,i:block-blinkwait100-blinkon200-blinkoff250,r-cr:hor20,o:block"

vim.opt.number = true
vim.opt.relativenumber = true

vim.opt.autoindent = true             -- Indent: Copy indent from current line when starting new line
vim.opt.clipboard = "unnamedplus"     -- Sync clipboard between OS and Neovim
vim.opt.colorcolumn = "120"           -- Show vertical bar to indicate 120 chars

-- Diff
vim.opt.diffopt:append("algorithm:histogram") -- better hunk matching than the default myers
vim.opt.fillchars:append({ diff = "╱" })      -- diagonal hatching instead of a wall of `-`

-- Search
vim.opt.ignorecase = true             -- Ignore case
vim.opt.smartcase = true              -- unless uppercase chars are given

-- better up/down
vim.keymap.set({ "n", "x" }, "j", "v:count == 0 ? 'gj' : 'j'", { desc = "Down", expr = true, silent = true })
vim.keymap.set({ "n", "x" }, "<Down>", "v:count == 0 ? 'gj' : 'j'", { desc = "Down", expr = true, silent = true })
vim.keymap.set({ "n", "x" }, "k", "v:count == 0 ? 'gk' : 'k'", { desc = "Up", expr = true, silent = true })
vim.keymap.set({ "n", "x" }, "<Up>", "v:count == 0 ? 'gk' : 'k'", { desc = "Up", expr = true, silent = true })

-- Move to window using the <ctrl> hjkl keys
vim.keymap.set("n", "<C-h>", "<C-w>h", { desc = "Go to Left Window", remap = true })
vim.keymap.set("n", "<C-j>", "<C-w>j", { desc = "Go to Lower Window", remap = true })
vim.keymap.set("n", "<C-k>", "<C-w>k", { desc = "Go to Upper Window", remap = true })
vim.keymap.set("n", "<C-l>", "<C-w>l", { desc = "Go to Right Window", remap = true })

-- Re-center the window when jumping up or down
vim.keymap.set("n", "<C-d>", "<C-d>zz")
vim.keymap.set("n", "<C-u>", "<C-u>zz")

-- Resize window height using alt arrow keys
vim.keymap.set("n", "<M-Up>", "<cmd>resize +2<cr>", { desc = "Increase Window Height" })
vim.keymap.set("n", "<M-Down>", "<cmd>resize -2<cr>", { desc = "Decrease Window Height" })
-- Resize width with _ and +
vim.keymap.set("n", "_", "<cmd>vertical resize -2<cr>", { desc = "Decrease Window Width" })
vim.keymap.set("n", "+", "<cmd>vertical resize +2<cr>", { desc = "Increase Window Width" })

-- Add undo break-points
vim.keymap.set("i", ",", ",<c-g>u")
vim.keymap.set("i", ".", ".<c-g>u")
vim.keymap.set("i", ";", ";<c-g>u")

-- save file
vim.keymap.set({ "i", "x", "n", "s" }, "<C-s>", "<cmd>w<cr><esc>", { desc = "Save File" })

-- better indenting
vim.keymap.set("v", "<", "<gv")
vim.keymap.set("v", ">", ">gv")

-- buffers
local ui = require("util.ui")
vim.keymap.set("n", "<leader>bd", ui.bufremove, { desc = "Delete Buffer" })

-- Highlight when yanking (copying) text
--  Try it with `yap` in normal mode
--  See `:help vim.highlight.on_yank()`
vim.api.nvim_create_autocmd('TextYankPost', {
  desc = 'Highlight when yanking (copying) text',
  group = vim.api.nvim_create_augroup('kickstart-highlight-yank', { clear = true }),
  callback = function()
    vim.highlight.on_yank()
  end,
})

-- Clear highlights on search when pressing <Esc> in normal mode
--  See `:help hlsearch`
vim.keymap.set('n', '<Esc>', '<cmd>nohlsearch<CR>')

-- Quickfix
vim.keymap.set("n", "<M-j>", "<cmd>cnext<CR>", { desc = "qfix next" })
vim.keymap.set("n", "<M-k>", "<cmd>cprev<CR>", { desc = "qfix prev" })
vim.keymap.set("n", "<M-c>", "<cmd>cclose<CR>", { desc = "qfix close" })
vim.keymap.set("n", "<M-o>", "<cmd>copen<CR>", { desc = "qfix open" })
-- :cdo s/find/replace/gc will find and replace over every item in the quickfix list

-- views can only be fully collapsed with the global statusline
vim.opt.laststatus = 3

-- Yank filepath of the current buffer
vim.keymap.set({ "n", "v" }, "<leader>yp", function()
  local path = vim.fn.expand('%:p')
  local root = vim.fn.systemlist('git rev-parse --show-toplevel')[1]
  if root and path:find(root, 1, true) == 1 then
    vim.fn.setreg('*', path:sub(#root + 2))
  else
    vim.fn.setreg('*', vim.fn.expand('%:.'))
  end
end, { desc = "[Y]ank [P]ath of file (relative to root dir)" })
vim.keymap.set({ "n", "v" }, "<leader>yP", "<cmd>let @* = expand('%:p')<CR>", { desc = "[Y]ank [P]ath of file (absolute path)" })

-- Add filetypes for Open API specs, since they aren't detected automatically:
vim.filetype.add({
  pattern = {
    ["openapi.*%.ya?ml"] = "yaml.openapi",
    ["openapi.*%.json"] = "json.openapi",
  },
})
