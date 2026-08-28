return {
	cmd = { "pyright-langserver", "--stdio" },
	filetypes = { "python" },
	root_markers = { ".git", "pyrightconfig.json", "pyproject.toml" },
	settings = {
		python = {
			venvPath = ".",
			venv = ".venv",
			pythonPath = ".venv/bin/python",
		},
	},
}
