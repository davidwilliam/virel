# Editor integration

The Virel language server (`virel lsp`) speaks standard LSP over stdio,
so any LSP client works. It provides component and prop autocomplete,
prop documentation on hover, invalid-prop diagnostics, design-token and
route completion, and go-to-definition from a route string to its page
function (SPEC 15.4).

## Neovim (built-in LSP)

```lua
vim.api.nvim_create_autocmd("FileType", {
  pattern = "python",
  callback = function()
    vim.lsp.start({
      name = "virel",
      cmd = { "virel", "lsp" },
      root_dir = vim.fs.dirname(vim.fs.find({ "virel.toml" }, {
        upward = true })[1]),
    })
  end,
})
```

## VS Code

The `vscode/` folder is a minimal extension that launches `virel lsp`
for Python files in a Virel project. Load it with "Run Extension" from
the Extensions view, or package it with `vsce`.

## PyCharm and other JetBrains IDEs

Use the LSP4IJ plugin and register a new language server whose command
is `virel lsp`, scoped to Python files. JetBrains reads the same
capabilities as every other client.

## Generic LSP clients

Any client that launches a command and speaks LSP over stdio works.
Command: `virel lsp`. It requires no arguments and finds the project
from the working directory's `virel.toml`.
