return {
	{
		"lewis6991/gitsigns.nvim",
		config = function()
			require("gitsigns").setup({
				current_line_blame = true, -- Toggle with `:Gitsigns toggle_current_line_blame`
				current_line_blame_opts = {
					virt_text = true,
					virt_text_pos = "eol", -- 'eol' | 'overlay' | 'right_align'
					delay = 1000,
					ignore_whitespace = false,
					virt_text_priority = 100,
					use_focus = true,
				},
			})
      vim.keymap.set("n", "<leader>gp", ":Gitsigns preview_hunk<CR>", { desc = "Git preview hunk" })
      vim.keymap.set("n", "<leader>gr", ":Gitsigns reset_hunk<CR>", { desc = "Git reset hunk" })
		end,
	},
  {
    "sindrets/diffview.nvim",
    keys = {
      { "<leader>gd", "<cmd>DiffviewOpen<cr>", desc = "Open diffview" },
    },
    opts = {
      enhanced_diff_hl = true, -- distinguish "deleted" from "changed-to" regions
      view = {
        default = { layout = "diff2_horizontal", winbar_info = true },
        merge_tool = {
          layout = "diff3_mixed", -- OURS | THEIRS on top, merge result below
          disable_diagnostics = true,
          winbar_info = true,
        },
        file_history = { layout = "diff2_horizontal", winbar_info = true },
      },
      hooks = {
        diff_buf_read = function(bufnr)
          vim.opt_local.wrap = false
          vim.opt_local.list = false
          vim.opt_local.cursorline = true
          vim.opt_local.number = true
          vim.opt_local.relativenumber = false
        end,
      },
    },
  },
	{
		"ruifm/gitlinker.nvim",
		dependencies = { "nvim-lua/plenary.nvim" },
		keys = {
			{
				mode = "n",
				desc = "[G]it [Y]ank a permalink to file",
				silent = true,
				"<leader>gy",
				function()
					require("gitlinker").get_buf_range_url("n")
				end,
			},
			{
				mode = "v",
				desc = "[G]it [Y]ank a permalink to selected lines",
				silent = true,
				"<leader>gy",
				function()
					require("gitlinker").get_buf_range_url("v")
				end,
			},
			{
				mode = "n",
				desc = "[G]it open file in browser",
				silent = true,
				"<leader>gY",
				function()
					local gitlinker = require("gitlinker")
					local actions = require("gitlinker.actions")
					gitlinker.get_buf_range_url("n", { action_callback = actions.open_in_browser })
				end,
			},
			{
				mode = "v",
				desc = "[G]it open lines in browser",
				silent = true,
				"<leader>gY",
				function()
					local gitlinker = require("gitlinker")
					local actions = require("gitlinker.actions")
					gitlinker.get_buf_range_url("v", { action_callback = actions.open_in_browser })
				end,
			},
		},
		opts = {},
	},
}
