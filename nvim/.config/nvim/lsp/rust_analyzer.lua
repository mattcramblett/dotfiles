return {
	cmd = { "rust-analyzer" },
	root_markers = { ".git", "cargo.toml" },
	filetypes = { "rust" },
	settings = {
		["rust-analyzer"] = {
      check = { command = "clippy", features = "all" },
		},
	},
}
