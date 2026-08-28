return {
	"ThePrimeagen/harpoon",
	branch = "harpoon2",
	dependencies = { "nvim-lua/plenary.nvim"
    -- , "nvim-telescope/telescope.nvim" 
  },
	settings = {},
	config = function()
    local harpoon = require("harpoon")
		harpoon:setup()

    --
		-- NOTE: this integrates with Telescope. Only commented out because the `remove_at` wasn't working right
    --
		-- local conf = require("telescope.config").values
		-- local function toggle_telescope(harpoon_files)
		--     -- Collect Harpoon items to return in Telescope results
		--     local make_finder = function()
		--       local paths = {}
		--       for _, item in ipairs(harpoon_files.items) do
		--         table.insert(paths, item.value)
		--       end
		--
		--       return require("telescope.finders").new_table(
		--         {
		--           results = paths
		--         }
		--       )
		--     end
		--
		-- 	require("telescope.pickers")
		-- 		.new({}, {
		-- 			prompt_title = "Harpoon",
		-- 	       finder = make_finder(),
		-- 			previewer = conf.file_previewer({}),
		-- 			sorter = conf.generic_sorter({}),
		-- 			attach_mappings = function(prompt_buffer_number, map)
		-- 				map(
		-- 					"i",
		-- 					"<C-d>", -- Remove from harpoon list
		-- 					function()
		-- 						local state = require("telescope.actions.state")
		-- 						local selected_entry = state.get_selected_entry()
		-- 						local current_picker = state.get_current_picker(prompt_buffer_number)
		--
		-- 						harpoon:list():remove_at(selected_entry.index)
		-- 						current_picker:refresh(make_finder())
		-- 					end
		-- 				)
		--
		-- 				return true
		-- 			end,
		-- 		})
		-- 		:find()
		-- end

		-- Open the list
		vim.keymap.set("n", ";", function()
			-- toggle_telescope(harpoon:list())
      harpoon.ui:toggle_quick_menu(harpoon:list())
		end, { desc = "Harpoon list" })

		-- Add buffer to harpoon list
		vim.keymap.set("n", "<leader>a", function()
			harpoon:list():add()
		end)

		vim.keymap.set("n", "<leader>d", function()
			harpoon:list():remove()
		end)

		-- Next harpoon file
		vim.keymap.set("n", "<C-N>", function()
			harpoon:list():next()
		end)

		-- Previous harpoon file
		vim.keymap.set("n", "<C-P>", function()
			harpoon:list():prev()
		end)

		-- Extensions
		harpoon:extend({
			UI_CREATE = function(cx)
				-- Open in vertical split
				vim.keymap.set("n", "<C-v>", function()
					harpoon.ui:select_menu_item({ vsplit = true })
				end, { buffer = cx.bufnr })

				-- Open in split
				vim.keymap.set("n", "<C-x>", function()
					harpoon.ui:select_menu_item({ split = true })
				end, { buffer = cx.bufnr })
			end,
		})
	end,
}
