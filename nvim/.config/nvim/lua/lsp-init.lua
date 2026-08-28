local servers = {
	"rust_analyzer",
	"gopls",
	"kotlin_language_server",
	"lua_ls",
	"sorbet",
	"tailwindcss",
	"ts_ls",
	"vacuum",
	"ruby-lsp",
}

local servers_to_install = vim.tbl_filter(function(server)
	return server ~= "ruby-lsp" and server ~= "sorbet"
end, servers)

local mason_lspconfig = require("mason-lspconfig")
-- auto install with mason-lspconfig
mason_lspconfig.setup({
	automatic_installation = true,
	ensure_installed = servers_to_install,
})

-- LSP keymaps
vim.keymap.set("n", "M", vim.diagnostic.open_float, { desc = "Diagnostics - open float window" })
vim.keymap.set("n", "K", vim.lsp.buf.hover, { desc = "LSP Hover" })
vim.keymap.set(
	"n",
	".",
	function ()
	  vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled())
	end,
	{ desc = "LSP toggle inlay hints" }
)
vim.keymap.set("n", "gd", vim.lsp.buf.definition, { desc = "[G]oto [D]efinition" })
vim.keymap.set("n", "gr", function()
	require("telescope.builtin").lsp_references({
		prompt_title = "LSP References",
		path_display = { "shorten" },
	})
end, { desc = "[G]oto [R]eferences" })
vim.keymap.set("n", "gI", require("telescope.builtin").lsp_implementations, { desc = "[G]oto [I]mplementation" })
vim.keymap.set({ "n", "v" }, "<leader>ca", vim.lsp.buf.code_action, { desc = "[C]ode [A]ctions" })

vim.lsp.enable(servers)

-- Add LSP as a completion source
vim.api.nvim_create_autocmd("LspAttach", {
	callback = function(ev)
		local client = vim.lsp.get_client_by_id(ev.data.client_id)
		if client == nil then
			return
		end

		if client:supports_method("textDocument/completion") then
			vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = false })
		end

    -- keep inlay hints disabled by default, toggled with N
		if client:supports_method("textDocument/inlayHint") then
			vim.lsp.inlay_hint.enable(false, { bufnr = ev.bufnr })
		end

		-- Below: sorbet compatibility with ruby-lsp
		-- if client.name ~= "sorbet" then
		--   return
		-- end

		-- Disable sorbet if file is in a non-sorbet project
		-- look for "sorbet/config" upward from the file on disk
		-- local root = vim.fs.dirname(vim.fs.find({'sorbet/config'}, { upward = true })[1])
		-- if not root then
		--   vim.lsp.stop_client(client.id, { force = true })
		--   return
		-- end

		-- Disable Sorbet if the first line has "# typed: false"
		-- local first_line = vim.api.nvim_buf_get_lines(ev.buf, 0, 1, false)[1]
		-- if first_line and first_line:match("#%s*typed:%s*false") then
		--   vim.lsp.stop_client(client.id, { force = true })
		--   return
		-- end
	end,
})
