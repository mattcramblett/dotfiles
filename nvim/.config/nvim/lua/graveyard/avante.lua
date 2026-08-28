-- Disabling Avante for now.
if false and vim.env.OPENAI_API_KEY then
	return {
		"yetone/avante.nvim",
		event = "VeryLazy",
		version = false,
		opts = {
			-- NOTE: These opts only take effect if you remove the `config` function
			provider = "openai",
			openai = {
				endpoint = "https://api.openai.com/v1",
				model = "o3-mini",
				timeout = 60000, -- Timeout in milliseconds, increase this for reasoning models
				temperature = 0,
				max_completion_tokens = 16384, -- Increase this to include reasoning tokens (for reasoning models)
				reasoning_effort = "medium", -- low|medium|high, only used for reasoning models
			},
			behavior = {
				enable_token_counting = false,
				-- auto_suggestions = false, -- Experimental stage
				-- auto_set_highlight_group = true,
				-- auto_set_keymaps = true,
				-- auto_apply_diff_after_generation = false,
				-- support_paste_from_clipboard = false,
				-- minimize_diff = true, -- Whether to remove unchanged lines when applying a code block
				-- enable_cursor_planning_mode = false, -- Whether to enable Cursor Planning Mode. Default to false.
				-- enable_claude_text_editor_tool_mode = false, -- Whether to enable Claude Text Editor Tool
			},
		},
		-- if you want to build from source then do `make BUILD_FROM_SOURCE=true`
		build = "make",
		dependencies = {
			"nvim-treesitter/nvim-treesitter",
			"stevearc/dressing.nvim",
			"nvim-lua/plenary.nvim",
			"MunifTanjim/nui.nvim",
			--- The below dependencies are optional,
			"echasnovski/mini.pick", -- for file_selector provider mini.pick
			"nvim-telescope/telescope.nvim", -- for file_selector provider telescope
			"hrsh7th/nvim-cmp", -- autocompletion for avante commands and mentions
			"ibhagwan/fzf-lua", -- for file_selector provider fzx-api-key header is requiredf
			"nvim-tree/nvim-web-devicons", -- or echasnovski/mini.icons
			"zbirenbaum/copilot.lua", -- for providers='copilot'
			{
				-- support for image pasting
				"HakonHarnes/img-clip.nvim",
				event = "VeryLazy",
				opts = {
					-- recommended settings
					default = {
						embed_image_as_base64 = false,
						prompt_for_file_name = false,
						drag_and_drop = {
							insert_mode = true,
						},
						-- required for Windows users
						use_absolute_path = true,
					},
				},
			},
		},
		-- Uncomment to use Bedrock/Claude
		-- config = function()
		-- 	local bedrock_util = require("util.aws-bedrock")
		-- 	vim.api.nvim_create_user_command("Bedrock", bedrock_util.update_bedrock_keys, {})
		--     bedrock_util.try_to_set_bedrock_keys()
		--
		--     -- System should be using cURL version 8.12 or above
		-- 	require("avante").setup({
		-- 		provider = "bedrock",
		-- 		bedrock = {
		--         model = "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
		-- 			timeout = 60000,
		-- 			temperature = 0,
		-- 			max_tokens = 16384,
		-- 			reasoning_effort = "medium",
		-- 		},
		-- 	})
		-- end,
	}
else
	return {}
end
