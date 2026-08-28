return {
	{
		"nvim-treesitter/nvim-treesitter",
		branch = "main",
		lazy = false, -- the main branch does not support lazy-loading
		build = ":TSUpdate",
		config = function()
			require("nvim-treesitter").install({
				"python",
				"javascript",
				"typescript",
				"tsx",
				"ruby",
				"kotlin",
				"java",
				"rust",
				"zig",
				"lua",
				"json",
				"yaml",
				"bash",
			})

			-- The main branch no longer enables highlighting for us, so start it
			-- per-buffer for any filetype that has a parser and queries installed.
			vim.api.nvim_create_autocmd("FileType", {
				group = vim.api.nvim_create_augroup("treesitter-highlight", { clear = true }),
				callback = function(args)
					local lang = vim.treesitter.language.get_lang(args.match)
					if lang and vim.treesitter.query.get(lang, "highlights") then
						vim.treesitter.start(args.buf, lang)
					end
				end,
			})
		end,
	},
	{
		"RRethy/nvim-treesitter-endwise",
		event = "InsertEnter",
	},
  -- Automatically add closing tags for HTML and JSX
  {
    "windwp/nvim-ts-autotag",
    opts = {},
  },
}
