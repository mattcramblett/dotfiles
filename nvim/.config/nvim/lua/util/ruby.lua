local M = {}

function M.find_spec()
	local basename = vim.fn.expand("%:t:r")
	local pattern = basename .. "*_spec.rb"
	local results = vim.fn.systemlist("rg --files --glob '" .. pattern .. "'")
	if #results == 0 then
		vim.notify("No spec files found for " .. basename, vim.log.levels.WARN)
	elseif #results == 1 then
		vim.cmd.edit(results[1])
	else
		vim.fn.setqflist({}, "r", {
			title = "Specs for " .. basename,
			items = vim.tbl_map(function(f)
				return { filename = f }
			end, results),
		})
		vim.cmd.copen()
	end
end

function M.find_source()
	local basename = vim.fn.expand("%:t:r")
	local source_name = basename:gsub("_spec$", "") .. ".rb"
	local results = vim.fn.systemlist("rg --files --glob '**/" .. source_name .. "'")
	if #results == 0 then
		vim.notify("No source file found for " .. source_name, vim.log.levels.WARN)
	elseif #results == 1 then
		vim.cmd.edit(results[1])
	else
		vim.fn.setqflist({}, "r", {
			title = "Source: " .. source_name,
			items = vim.tbl_map(function(f)
				return { filename = f }
			end, results),
		})
		vim.cmd.copen()
	end
end

return M
