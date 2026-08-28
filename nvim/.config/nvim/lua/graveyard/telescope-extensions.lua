--
-- CUSTOM PICKERS
--
return {
	"axkirillov/easypick.nvim",
	config = function()
		-- Setup pickers with arbitray commands
		local get_default_branch = "git remote show origin | grep 'HEAD branch' | cut -d' ' -f5"
		local base_branch = vim.fn.system(get_default_branch) or "main"
		local easypick = require("easypick")
		local previewers = require("telescope.previewers")
		easypick.setup({
			pickers = {
				-- diff current branch with base_branch and show files that changed with respective diffs in preview
				{
					name = "branch_changes",
					command = "git diff --name-only $(git merge-base HEAD "
						.. base_branch
						.. " ) && git ls-files --others --exclude-standard",
					cwd = vim.trim(vim.fn.system("git rev-parse --show-toplevel")),
					previewer = previewers.new_termopen_previewer({
						get_command = function(entry)
							local filepath = entry.path or entry.value
							return { "git", "diff", base_branch, "--", filepath }
						end,
					}),
				},
			},
		})

		vim.keymap.set("n", ".", "<cmd>:Easypick branch_changes<CR>", { desc = "Changed files on branch" })
	end,
}
