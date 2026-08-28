-- Formatter
return {
	"stevearc/conform.nvim",
	cmd = { "ConformInfo" },
	keys = {
		{
			"<leader>ff",
			function()
				require("conform").format({ async = true })
			end,
			mode = "n",
			desc = "[F]ormat [F]ile",
		},
	},
	config = function()
		require("conform").setup({
			formatters_by_ft = {
				lua = { "stylua" },
				ruby = { "rubocop" },
				kotlin = { "ktlint" },
				java = { "google-java-format" },
				go = { "gofmt" },
				rust = { "rustfmt", lsp_format = "fallback" },
				typescript = { "prettier" },
				typescriptreact = { "prettier" },
				javascript = { "prettier" },
				javascriptreact = { "prettier" },
				markdown = { "deno_fmt" },
				["_"] = { "trim_whitespace" }, -- filetype with no formatter
			},
			default_format_opts = {
				lsp_format = "fallback",
			},
			formatters = {
				rubocop = {
					command = "bundle",
					args = {
						"exec",
						"rubocop",
						"-a",
						"-f",
						"quiet",
						"--stderr",
						"--stdin",
						"$FILENAME",
					},
					stdin = true,
				},
			},
		})
	end,
}
