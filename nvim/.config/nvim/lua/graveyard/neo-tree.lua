return {
	"nvim-neo-tree/neo-tree.nvim",
	branch = "v3.x",
	dependencies = {
		"nvim-lua/plenary.nvim",
		"nvim-tree/nvim-web-devicons",
		"MunifTanjim/nui.nvim",
	},
	config = function()
		vim.keymap.set("n", "<leader>e", "<Cmd>Neotree toggle<CR>", { desc = "Toggle File Tree" }) -- toggle file tree explorer

    require("neo-tree").setup({
      filesystem = {
        follow_current_file = {
          enabled = true, -- This will find and focus the file in the active buffer every time
        },
        filtered_items = {
          hide_dotfiles = false,
          hide_gitignored = false,
        },
        group_empty_dirs = true,
      }
    })
	end,
}
