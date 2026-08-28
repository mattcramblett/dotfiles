local pickers = require "telescope.pickers"
local finders = require "telescope.finders"
local make_entry = require "telescope.make_entry"
local conf = require "telescope.config".values

local M = {}

local live_multigrep = function (opts)
  opts = opts or {}
  opts.cwd = opts.cwd or vim.uv.cwd()

  local finder = finders.new_async_job {
    command_generator = function(prompt)
      if not prompt or prompt == "" then
        return nil
      end

      local pieces = vim.split(prompt, "  ")
      local args = { "rg" }
      if pieces[1] then
        table.insert(args, "-e")
        table.insert(args, pieces[1])
      end

      -- default globs for certain projects
      if string.match(opts.cwd, "code/upstart_web$") then
        table.insert(args, "--glob")
        table.insert(args, "!*.rbi")
        table.insert(args, "--glob")
        table.insert(args, "!*.csv")
      end

      -- Allow input of additional globs to filter files, after search + double space.
      if pieces[2] and pieces[2] ~= "" then
        -- split the first part into multiple patterns and add each with -e
        local patterns = vim.split(pieces[2], "%s+")
        for _, pat in ipairs(patterns) do
          table.insert(args, "--glob")
          table.insert(args, pat)
        end
      end

      return vim.tbl_flatten {
        args,
        { "--color=never", "--no-heading", "--with-filename", "--line-number", "--column", "--smart-case" },
        opts.additional_args or {}
      }
    end,
    entry_maker = make_entry.gen_from_vimgrep(opts),
    cwd = opts.cwd,
  }

  pickers.new(opts, {
    debounce = 100,
    prompt_title = "Grep",
    finder = finder,
    previewer = conf.grep_previewer(opts),
    sorter = require("telescope.sorters").empty(),
    path_display = { "absolute" },
  }):find()
end

M.setup = function ()
  -- args to pass to ripgrep
  -- https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md#common-options
  vim.keymap.set("n", "<leader>s", live_multigrep, { desc = "Live grep (regex)" })

  vim.keymap.set("n", "<leader>/", function ()
    live_multigrep({ additional_args = { "--ignore-case", "--fixed-strings" } })
  end, { desc = "Live grep (words)" })
end

return M
