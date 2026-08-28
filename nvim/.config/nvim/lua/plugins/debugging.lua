return {
	{
		"mfussenegger/nvim-dap",
    dependencies = {
      "suketa/nvim-dap-ruby"
    },
		config = function()
			local dap = require("dap")
			vim.keymap.set("n", "<Leader>dt", dap.toggle_breakpoint, { desc = "[T]oggle breakpoint" })
			vim.keymap.set("n", "<Leader>dc", dap.continue, { desc = "[C]ontinue" })

      require("dap-ruby").setup()
		end,
	},
	{
		"rcarriga/nvim-dap-ui",
		dependencies = { "mfussenegger/nvim-dap", "nvim-neotest/nvim-nio" },
		config = function()
			local dap = require("dap")
			local dapui = require("dapui")

			dapui.setup()

			-- trigger ui when debugging events occur
			dap.listeners.before.attach.dapui_config = function()
				dapui.open()
			end
			dap.listeners.before.launch.dapui_config = function()
				dapui.open()
			end
			dap.listeners.before.event_terminated.dapui_config = function()
				dapui.close()
			end
			dap.listeners.before.event_exited.dapui_config = function()
				dapui.close()
			end
		end,
	},
	-- https://github.com/mfussenegger/nvim-dap/wiki/Debug-Adapter-installation
}
