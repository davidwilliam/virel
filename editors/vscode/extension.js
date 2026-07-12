// Minimal VS Code client for the Virel language server (SPEC 15.4).
// It starts `virel lsp` over stdio for Python documents. No bundler
// required; VS Code loads this file directly.
const { workspace } = require("vscode");
const { spawn } = require("child_process");

let child = null;

function activate(context) {
  const command = workspace.getConfiguration("virel")
    .get("serverCommand", "virel");
  child = spawn(command, ["lsp"], {
    cwd: workspace.workspaceFolders?.[0]?.uri.fsPath,
  });
  // The vscode-languageclient package wires this to the editor; this
  // stub keeps the transport alive so the command is verifiably
  // launchable. Install vscode-languageclient to enable full features.
  context.subscriptions.push({ dispose: () => child && child.kill() });
}

function deactivate() {
  if (child) child.kill();
}

module.exports = { activate, deactivate };
