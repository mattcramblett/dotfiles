-- NOTE: https://block.github.io/goose/docs/getting-started/installation/
return {
	{
		"azorng/goose.nvim",
		config = function()
			require("goose").setup({
				default_global_keymaps = false,
				keymap = {
					global = {
						toggle = "<leader>gg", -- Open goose. Close if opened
						open_input = "<leader>gi", -- Opens and focuses on input window on insert mode
						open_input_new_session = "<leader>gI", -- Opens and focuses on input window on insert mode. Creates a new session
						open_output = "<leader>go", -- Opens and focuses on output window
						toggle_focus = "<leader>gt", -- Toggle focus between goose and last window
						close = "<leader>gq", -- Close UI windows
						toggle_fullscreen = "<leader>gf", -- Toggle between normal and fullscreen mode
						select_session = "<leader>gs", -- Select and load a goose session
						goose_mode_chat = "<leader>gmc", -- Set goose mode to `chat`. (Tool calling disabled. No editor context besides selections)
						goose_mode_auto = "<leader>gma", -- Set goose mode to `auto`. (Default mode with full agent capabilities)
						-- configure_provider = "<leader>gp", -- Quick provider and model switch from predefined list
						-- diff_open = "<leader>gd", -- Opens a diff tab of a modified file since the last goose prompt
						-- diff_next = "<leader>g]", -- Navigate to next file diff
						-- diff_prev = "<leader>g[", -- Navigate to previous file diff
						-- diff_close = "<leader>gc", -- Close diff view tab and return to normal editing
						-- diff_revert_all = "<leader>gra", -- Revert all file changes since the last goose prompt
						-- diff_revert_this = "<leader>grt", -- Revert current file changes since the last goose prompt
					},
					window = {
						submit = "<cr>", -- Submit prompt
						close = "<esc>", -- Close UI windows
						stop = "<C-c>", -- Stop goose while it is running
						next_message = "]]", -- Navigate to next message in the conversation
						prev_message = "[[", -- Navigate to previous message in the conversation
						mention_file = "@", -- Pick a file and add to context. See File Mentions section
						toggle_pane = "<tab>", -- Toggle between input and output panes
						prev_prompt_history = "<up>", -- Navigate to previous prompt in history
						next_prompt_history = "<down>", -- Navigate to next prompt in history
					},
				},
				providers = {
					openai = "gpt-5-mini",
				},
			})
		end,
		dependencies = {
			"nvim-lua/plenary.nvim",
			{
				"MeanderingProgrammer/render-markdown.nvim",
				opts = {
					anti_conceal = { enabled = false },
				},
			},
		},
	},
	-- {
	-- 	"zbirenbaum/copilot.lua",
	-- 	cmd = "Copilot",
	-- 	event = "InsertEnter",
	-- 	suggestion = {
	-- 		enabled = true,
	-- 		auto_trigger = false,
	-- 		keymap = {
	-- 			accept = "<M-l>",
	-- 			accept_word = false,
	-- 			accept_line = false,
	-- 			next = "<M-]>",
	-- 			prev = "<M-[>",
	-- 			dismiss = "<C-]>",
	-- 		},
	-- 	},
	-- 	copilot_model = "",
	-- 	panel = { enabled = false },
	-- 	config = function()
	-- 		-- run :Copilot auth
	-- 		require("copilot").setup({
	-- 			copilot_node_command = vim.fn.expand("$HOME") .. "/.asdf/installs/nodejs/22.12.0/bin/node",
	-- 		})
	--
	-- 		-- Disable Copilot when Blink menu is open
	-- 		vim.api.nvim_create_autocmd("User", {
	-- 			pattern = "BlinkCmpMenuOpen",
	-- 			callback = function()
	-- 				vim.b.copilot_suggestion_hidden = true
	-- 			end,
	-- 		})
	--
	-- 		-- Re-enable when Blink menu closes
	-- 		vim.api.nvim_create_autocmd("User", {
	-- 			pattern = "BlinkCmpMenuClose",
	-- 			callback = function()
	-- 				vim.b.copilot_suggestion_hidden = false
	-- 			end,
	-- 		})
	-- 	end,
	-- },
	-- 	not working with blink
	-- 	{
	-- 		"zbirenbaum/copilot-cmp",
	-- 		config = function()
	-- 			require("copilot_cmp").setup()
	-- 		end,
	-- 	},
}
