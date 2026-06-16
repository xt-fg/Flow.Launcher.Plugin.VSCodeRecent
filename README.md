# VSCode Recent — Flow Launcher plugin

Quickly find and open your recent VS Code folders and workspaces from [Flow Launcher](https://github.com/Flow-Launcher/Flow.Launcher).

Type `{`, see your recently-opened folders/workspaces (most recent first), filter by name or path, and press <kbd>Enter</kbd> to open in VS Code.

## Why this plugin
Recent VS Code builds (2026+) no longer store the recently-opened list in
`state.vscdb` under `history.recentlyOpenedPathsList` — the key the older
VSCodeWorkspaces plugins depend on, so they suddenly show nothing. This plugin
reads VS Code's **current** storage
(`User/globalStorage/storage.json`: `profileAssociations` / `backupWorkspaces` /
`windowsState`) and still falls back to the legacy `state.vscdb` key for older
versions.

## Install
**From the Flow plugin store** (once approved):
```
pm install VSCode Recent
```

**Directly from the latest release:**
```
pm install https://github.com/xt-fg/Flow.Launcher.Plugin.VSCodeRecent/releases/latest/download/Flow.Launcher.Plugin.VSCodeRecent.zip
```
Then restart Flow Launcher.

## Usage
- Type the action keyword `{` to list recent workspaces (most-recent first).
- Type part of a folder name or path to filter.
- <kbd>Enter</kbd> — open in VS Code.
- Context menu (<kbd>Ctrl</kbd>+<kbd>O</kbd> / <kbd>Shift</kbd>+<kbd>Enter</kbd>):
  Open in new window · Reveal in File Explorer · Copy path.

## Features
- Pure Python standard library — **zero third-party dependencies**.
- Reads the modern `storage.json`; legacy `state.vscdb` fallback.
- Recency-sorted (by `workspaceStorage` timestamps).
- Automatically hides folders that no longer exist.
- Local (`file://`) and remote (`vscode-remote://` — WSL / SSH / Dev Container / Codespaces).
- Multiple editors: VS Code, VS Code Insiders, VSCodium (extend via `EDITORS` in `main.py`).
- Unicode-safe output — non-ASCII paths never crash the plugin.

## Requirements
- Windows, with Flow Launcher's Python configured (Settings → General → Python).
- The `code` command on `PATH`, or VS Code in a standard install location.

## Development
Run it on WSL/Linux against your Windows VS Code data by mapping drives:
```bash
APPDATA=/mnt/c/Users/<you>/AppData/Roaming VSCWS_DRIVE_MAP=/mnt \
  python3 main.py '{"method":"query","parameters":[""]}'
```
`VSCWS_DRIVE_MAP` is a test-only hook (maps `D:\x` → `/mnt/d/x` for existence
checks) and has no effect on Windows.

## License
MIT
