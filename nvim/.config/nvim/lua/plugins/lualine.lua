return {
	"nvim-lualine/lualine.nvim",
	config = function()
    local theme = require("lualine.themes.onedark")
    theme.normal.b.bg = '#05183d'
    theme.normal.c.bg = '#020a1a'

		require("lualine").setup({
			options = {
				theme = theme,
			},
			sections = {
				lualine_a = {
					{
						"filename",
						file_status = true,
						newfile_status = true,
						path = 3,
						shorting_target = 42,
					},
				},
			},
		})
	end,
}
