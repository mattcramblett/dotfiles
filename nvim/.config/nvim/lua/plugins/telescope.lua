return {
	{
		"nvim-telescope/telescope.nvim",
		dependencies = {
			"nvim-lua/plenary.nvim",
			"BurntSushi/ripgrep",
			{ "nvim-tree/nvim-web-devicons", enabled = vim.g.have_nerd_font },
			{ "nvim-telescope/telescope-ui-select.nvim" },
			{ -- If encountering errors, see telescope-fzf-native README for installation instructions
				"nvim-telescope/telescope-fzf-native.nvim",

				-- `build` is used to run some command when the plugin is installed/updated.
				-- This is only run then, not every time Neovim starts up.
				build = "make",

				-- `cond` is a condition used to determine whether this plugin should be
				-- installed and loaded.
				cond = function()
					return vim.fn.executable("make") == 1
				end,
			},
		},
		config = function()
			local builtin = require("telescope.builtin")

			require("telescope").setup({
				extensions = {
					["ui-select"] = {
						require("telescope.themes").get_dropdown(),
					},
					fzf = {
						-- fuzzy = false, -- only exact matching
						case_mode = "ignore_case", -- "smart_case", "ignore_case" or "respect_case"
						override_generic_sorter = true, -- use fzf for non-file pickers
						override_file_sorter = true, -- use fzf for file pickers too
					},
				},
				defaults = {
					mappings = {
						i = {
							["<C-y>"] = require("telescope.actions.layout").toggle_preview,
						},
					},
					layout_config = {
						horizontal = { preview_width = 0.5 },
					},
				},
				pickers = {
					buffers = {
						theme = "ivy",
						show_all_buffers = true,
						sort_lastused = true,
						previewer = true,
						sorter = require("telescope").extensions.fzf.native_fzf_sorter({
							case_mode = "ignore_case", -- or "smart_case"/"respect_case"
						}),
						mappings = {
							i = {
								["<c-d>"] = "delete_buffer",
							},
						},
					},
					find_files = {
						theme = "ivy",
						-- `hidden = true` will still show the inside of `.git/` as it's not `.gitignore`d.
						-- `-i` for case-insensitive
						-- `-F` == `--fixed-strings`, meaning no regex and literal strings
						find_command = {
							"rg",
							"--files",
							"--hidden",
							"--glob",
							"!**/.git/*",
							"--glob",
							"!*.rbi",
							"-i",
							"-F",
						},
					},
				},
			})

			require("telescope").load_extension("fzf")
			require("telescope").load_extension("ui-select")
			require("config.telescope.multigrep").setup()

			vim.keymap.set("n", "<leader>o", builtin.find_files, { desc = "Find files" }) -- search for file by name
			vim.keymap.set(
				"n",
				"<leader>?",
				":!open https://regex101.com<CR><CR>",
				{ desc = "Open regex101 for help!" }
			)
			vim.keymap.set("n", "<leader>h", builtin.help_tags, { desc = "Search [H]elp" }) -- search help docs

			vim.keymap.set("n", ",", builtin.buffers, { desc = "Telescope buffers" })
			vim.keymap.set("n", "<leader>l", builtin.lsp_document_symbols, { desc = "LSP symbols" })
			vim.keymap.set("n", "<leader>cs", builtin.colorscheme, { desc = "Colorscheme" })

			-- Quickfix
			vim.keymap.set("n", "<leader>qq", builtin.quickfix, { desc = "Quickfix" })
			vim.keymap.set("n", "<leader>qh", builtin.quickfixhistory, { desc = "Quickfix history" })

			-- Marks
			vim.keymap.set("n", "<leader>m", builtin.marks, { desc = "Marks" })

			-- Keymaps
			vim.keymap.set("n", "<leader>k", builtin.keymaps, { desc = "Keymaps" })

			-- Quick searches
			vim.keymap.set("n", "gS", builtin.grep_string, { desc = "[G]o to [S]earch" })
			vim.keymap.set("n", "go", function()
				builtin.find_files({ default_text = vim.fn.expand("<cword>") })
			end, { desc = "[G]o to [O]pen file (search files with word)" })

			-- Ruby file navigation
			local ruby = require("util.ruby")
			vim.keymap.set("n", "<leader>fs", ruby.find_spec, { desc = "[F]ind [S]pec" })
			vim.keymap.set("n", "<leader>fS", ruby.find_source, { desc = "[F]ind [S]ource" })
		end,
	},
}
