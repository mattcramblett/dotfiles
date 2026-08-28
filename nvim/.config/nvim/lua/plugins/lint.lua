return {
	"mfussenegger/nvim-lint",
	config = function()
		local lint = require("lint")

		-- Linters by filetype
		lint.linters_by_ft = {
			ruby = { "rubocop" },
			kotlin = { "ktlint" },
			-- typescript = { "eslint_d", "eslint" }, -- covered by typescript-language-server
			javascript = { "eslint_d" },
			-- typescriptreact = { "eslint_d", "eslint" }, -- covered by typescript-language-server
			javascriptreact = { "eslint_d" },
			html = { "htmlhint" },
			css = { "stylelint" },
			scss = { "stylelint" },
			json = { "jsonlint" },
			markdown = { "alex" },
			python = { "pylint" },
			zsh = { "zsh" },
			sql = { "sqlfluff" },
		}

		local lint_augroup = vim.api.nvim_create_augroup("lint", { clear = true })

		local rubocop = lint.linters.rubocop
		rubocop.args = {
			"--require",
			"rubocop-rspec",
			"--cache", -- attempt to improve performance
		}

		-- Run linting on save
		vim.api.nvim_create_autocmd({ "BufRead", "BufWritePost" }, {
			group = lint_augroup,
			callback = function()
				-- try_lint without arguments runs the linters defined in `linters_by_ft`
				-- for the current filetype
				require("lint").try_lint(nil, { ignore_errors = true })
			end,
		})
	end,
}
