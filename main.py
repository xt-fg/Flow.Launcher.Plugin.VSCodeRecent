# -*- coding: utf-8 -*-
"""
VSCode Workspaces (Modern) — a Flow Launcher plugin.

Lists recently-opened VS Code folders / workspaces and opens them.

Why this exists: VS Code (2026+) stopped writing the recent list to
state.vscdb under `history.recentlyOpenedPathsList`, which the old C#/PowerToys
plugins rely on. This plugin reads the *current* source of truth,
`User/globalStorage/storage.json` (profileAssociations / backupWorkspaces /
windowsState), and still falls back to the legacy state.vscdb key for older
VS Code versions.

Pure standard library only — no third-party deps, so it can never fail with a
ModuleNotFoundError. Output is ASCII-escaped JSON, safe on any Windows codepage.
"""

import sys
import os
import json
import subprocess
from urllib.parse import unquote

try:
    import sqlite3  # only used for the legacy fallback
except Exception:  # pragma: no cover
    sqlite3 = None

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

ICON_APP = "Images/code-light.png"
ICON_FOLDER = "Images/folder.png"
ICON_REMOTE = "Images/monitor.png"
ICON_WORKSPACE = "Images/code-dark.png"

# Editors to scan: (folder under %APPDATA%, display tag, executable name)
EDITORS = [
    ("Code", "", "Code.exe"),
    ("Code - Insiders", "Insiders", "Code - Insiders.exe"),
    ("VSCodium", "VSCodium", "VSCodium.exe"),
]

# Test hook: when running outside Windows (e.g. WSL during development), set
# VSCWS_DRIVE_MAP=/mnt so local-path existence checks map "D:\x" -> "/mnt/d/x".
# Unset in production on Windows, so it is a no-op there.
_DRIVE_MAP = os.environ.get("VSCWS_DRIVE_MAP")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _appdata():
    return os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _exists_local(winpath):
    """Existence check for a Windows path, with a WSL test-mapping hook."""
    if _DRIVE_MAP and len(winpath) >= 2 and winpath[1] == ":":
        mapped = "%s/%s%s" % (_DRIVE_MAP.rstrip("/"), winpath[0].lower(),
                              winpath[2:].replace("\\", "/"))
        return os.path.exists(mapped)
    return os.path.exists(winpath)


def _is_workspace_file(uri):
    return uri.rstrip("/").lower().endswith(".code-workspace")


def classify(uri):
    """Turn a VS Code URI into a display record, or None if unusable."""
    if not uri or not isinstance(uri, str):
        return None

    wsfile = _is_workspace_file(uri)

    if uri.startswith("file:///"):
        path = unquote(uri[len("file:///"):])          # d:/work/code/first
        win = path.replace("/", "\\")                   # d:\work\code\first
        leaf = os.path.basename(path.rstrip("/")) or win
        name = os.path.splitext(leaf)[0] if wsfile else leaf
        return {
            "uri": uri, "remote": "", "local_path": win, "check": win,
            "name": name, "detail": win,
            "kind": "file" if wsfile else "folder",
        }

    if uri.startswith("vscode-remote://"):
        rest = uri[len("vscode-remote://"):]
        slash = rest.find("/")
        authority = rest[:slash] if slash >= 0 else rest
        path = unquote(rest[slash:]) if slash >= 0 else ""
        scheme, _, host = authority.partition("+")
        host = unquote(host)
        tag = {
            "wsl": "WSL", "ssh-remote": "SSH", "dev-container": "Dev Container",
            "attached-container": "Container", "codespaces": "Codespaces",
            "vsonline": "Codespaces", "tunnel": "Tunnel",
        }.get(scheme, scheme or "Remote")
        leaf = os.path.basename(path.rstrip("/")) or path or host
        name = os.path.splitext(leaf)[0] if wsfile else leaf
        remote = ("%s: %s" % (tag, host)) if host else tag
        return {
            "uri": uri, "remote": remote, "local_path": None, "check": None,
            "name": name or uri, "detail": "[%s] %s" % (remote, path or ""),
            "kind": "file" if wsfile else "folder",
        }

    # Any other scheme (vscode-vfs://, etc.) — show generically, can't verify.
    return {
        "uri": uri, "remote": "remote", "local_path": None, "check": None,
        "name": uri, "detail": uri, "kind": "folder",
    }


def _read_vscdb(path):
    """Legacy fallback: history.recentlyOpenedPathsList from state.vscdb."""
    out = []
    if not (sqlite3 and os.path.isfile(path)):
        return out
    try:
        import pathlib
        url = pathlib.Path(path).as_uri() + "?mode=ro&immutable=1"
        con = sqlite3.connect(url, uri=True, timeout=1.0)
        try:
            row = con.execute(
                "SELECT value FROM ItemTable "
                "WHERE key='history.recentlyOpenedPathsList'"
            ).fetchone()
        finally:
            con.close()
        if row and row[0]:
            for e in (json.loads(row[0]).get("entries") or []):
                if not isinstance(e, dict):
                    continue
                if e.get("folderUri"):
                    out.append(e["folderUri"])
                elif isinstance(e.get("workspace"), dict) and e["workspace"].get("configPath"):
                    out.append(e["workspace"]["configPath"])
    except Exception:
        pass
    return out


def _workspace_recency(ws_dir):
    """Map normalized-uri -> last-opened mtime, from workspaceStorage/*/workspace.json."""
    rec = {}
    if not os.path.isdir(ws_dir):
        return rec
    try:
        names = os.listdir(ws_dir)
    except Exception:
        return rec
    for name in names:
        d = os.path.join(ws_dir, name)
        wj = os.path.join(d, "workspace.json")
        try:
            if not os.path.isfile(wj):
                continue
            mtime = os.path.getmtime(d)
        except OSError:
            continue
        data = _load_json(wj)
        if not isinstance(data, dict):
            continue
        uri = data.get("folder") or data.get("workspace") or data.get("configuration")
        if isinstance(uri, dict):
            uri = uri.get("configPath")
        if isinstance(uri, str):
            key = unquote(uri).lower()
            if mtime > rec.get(key, 0):
                rec[key] = mtime
    return rec


def _gather_uris(storage):
    """Collect every workspace/folder URI mentioned in a storage.json dict."""
    uris = []
    if not isinstance(storage, dict):
        return uris
    pa = (storage.get("profileAssociations") or {}).get("workspaces") or {}
    if isinstance(pa, dict):
        uris.extend(pa.keys())
    bw = storage.get("backupWorkspaces") or {}
    for f in (bw.get("folders") or []):
        if isinstance(f, dict) and f.get("folderUri"):
            uris.append(f["folderUri"])
    for w in (bw.get("workspaces") or []):
        if isinstance(w, dict) and w.get("configPath"):
            uris.append(w["configPath"])
    ws = storage.get("windowsState") or {}
    windows = list(ws.get("openedWindows") or [])
    if ws.get("lastActiveWindow"):
        windows.append(ws["lastActiveWindow"])
    for w in windows:
        if not isinstance(w, dict):
            continue
        if w.get("folder"):
            uris.append(w["folder"])
        wk = w.get("workspace")
        if isinstance(wk, dict) and wk.get("configPath"):
            uris.append(wk["configPath"])
    return uris


def collect():
    """Return a recency-sorted list of workspace records across editors."""
    items = {}     # uri -> record
    recency = {}   # uri -> mtime
    for folder, tag, exe in EDITORS:
        data_dir = os.path.join(_appdata(), folder)
        if not os.path.isdir(data_dir):
            continue
        gstorage = os.path.join(data_dir, "User", "globalStorage")

        uris = _gather_uris(_load_json(os.path.join(gstorage, "storage.json")))
        uris += _read_vscdb(os.path.join(gstorage, "state.vscdb"))

        rec = _workspace_recency(os.path.join(data_dir, "User", "workspaceStorage"))

        for uri in uris:
            r = classify(uri)
            if r is None:
                continue
            if r["check"] is not None and not _exists_local(r["check"]):
                continue  # local path no longer exists
            r["exe"] = exe
            r["editor_tag"] = tag
            if uri not in items:
                items[uri] = r
            m = rec.get(unquote(uri).lower(), 0)
            if m > recency.get(uri, 0):
                recency[uri] = m

    out = list(items.values())
    out.sort(key=lambda r: (-recency.get(r["uri"], 0), r["name"].lower()))
    return out


# --------------------------------------------------------------------------- #
# query / results
# --------------------------------------------------------------------------- #
def _make_result(r):
    if r["kind"] == "file":
        icon = ICON_WORKSPACE
    elif r["remote"]:
        icon = ICON_REMOTE
    else:
        icon = ICON_FOLDER
    suffix = ""
    if r["kind"] == "file":
        suffix = "  [Workspace]"
    elif r["remote"]:
        suffix = "  [%s]" % r["remote"]
    return {
        "Title": r["name"] + suffix,
        "SubTitle": r["detail"],
        "IcoPath": icon,
        "JsonRPCAction": {
            "method": "open_workspace",
            "parameters": [r["uri"], r["kind"], r["exe"]],
        },
        "ContextData": [r["uri"], r["kind"], r["exe"], r["local_path"] or ""],
        "Score": 0,
    }


def do_query(query):
    tokens = (query or "").strip().lower().split()
    results = []
    for r in collect():
        hay = (r["name"] + " " + r["detail"]).lower()
        if tokens and not all(tok in hay for tok in tokens):
            continue
        results.append(_make_result(r))

    if not results:
        msg = "No VS Code workspaces found"
        sub = "Open a folder in VS Code first, then try again"
        if tokens:
            msg = "No workspace matches \"%s\"" % query.strip()
            sub = "Type part of a folder name or path"
        results.append({
            "Title": msg, "SubTitle": sub, "IcoPath": ICON_APP,
            "JsonRPCAction": {"method": "noop", "parameters": []},
        })
    return results


def context_menu(data):
    if not isinstance(data, list) or not data:
        return []
    uri = data[0]
    kind = data[1] if len(data) > 1 else "folder"
    exe = data[2] if len(data) > 2 else "Code.exe"
    local = data[3] if len(data) > 3 else ""
    items = [{
        "Title": "Open in new window",
        "SubTitle": uri,
        "IcoPath": ICON_APP,
        "JsonRPCAction": {"method": "open_new", "parameters": [uri, kind, exe]},
    }]
    if local:
        items.append({
            "Title": "Reveal in File Explorer",
            "SubTitle": local,
            "IcoPath": ICON_FOLDER,
            "JsonRPCAction": {"method": "reveal", "parameters": [local]},
        })
        items.append({
            "Title": "Copy path",
            "SubTitle": local,
            "IcoPath": ICON_FOLDER,
            "JsonRPCAction": {"method": "copy", "parameters": [local]},
        })
    return items


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #
_DETACHED = 0x00000008          # DETACHED_PROCESS
_NO_WINDOW = 0x08000000         # CREATE_NO_WINDOW


def find_editor_exe(exe_name="Code.exe"):
    cands = []
    for p in (os.environ.get("PATH") or "").split(os.pathsep):
        if not p:
            continue
        low = p.lower()
        if "code" in low or "vscodium" in low:
            parent = os.path.dirname(p.rstrip("\\/"))
            cands.append(os.path.join(parent, exe_name))   # <root>\Code.exe (bin in PATH)
            cands.append(os.path.join(p, exe_name))         # <root>\Code.exe (root in PATH)
    cands += [
        os.path.join(r"D:\softwares\Microsoft VS Code", exe_name),
        os.path.join(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code"), exe_name),
        os.path.join(r"C:\Program Files\Microsoft VS Code", exe_name),
    ]
    for c in cands:
        try:
            if os.path.isfile(c):
                return c
        except Exception:
            pass
    try:
        import shutil
        w = shutil.which("code") or shutil.which(os.path.splitext(exe_name)[0])
        if w:
            parent = os.path.dirname(os.path.dirname(w))
            c = os.path.join(parent, exe_name)
            return c if os.path.isfile(c) else w
    except Exception:
        pass
    return None


def _launch(uri, kind, exe_name, new_window=False):
    flag = "--file-uri" if kind == "file" else "--folder-uri"
    exe = find_editor_exe(exe_name or "Code.exe")
    args = []
    if new_window:
        args.append("--new-window")
    if exe:
        cmd = [exe] + args + [flag, uri]
        try:
            subprocess.Popen(cmd, creationflags=_DETACHED, close_fds=True)
            return
        except Exception:
            pass
    # Fallback: rely on `code` shim on PATH (suppress the cmd console window)
    try:
        subprocess.Popen(["cmd", "/c", "code"] + args + [flag, uri],
                         creationflags=_NO_WINDOW, close_fds=True)
    except Exception:
        pass


def open_workspace(uri, kind="folder", exe="Code.exe"):
    _launch(uri, kind, exe, new_window=False)


def open_new(uri, kind="folder", exe="Code.exe"):
    _launch(uri, kind, exe, new_window=True)


def reveal(local_path):
    try:
        subprocess.Popen(["explorer", local_path], close_fds=True)
    except Exception:
        pass


def copy(text):
    try:
        p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, creationflags=_NO_WINDOW)
        p.communicate(text.encode("utf-16-le"))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# JSON-RPC entry point
# --------------------------------------------------------------------------- #
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        request = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    except Exception:
        request = {}

    method = request.get("method", "query")
    params = request.get("parameters") or []

    try:
        if method == "query":
            print(json.dumps({"result": do_query(params[0] if params else "")}))
        elif method == "context_menu":
            print(json.dumps({"result": context_menu(params[0] if params else [])}))
        elif method == "open_workspace":
            open_workspace(*params)
        elif method == "open_new":
            open_new(*params)
        elif method == "reveal":
            reveal(*params)
        elif method == "copy":
            copy(*params)
        elif method == "noop":
            pass
        else:
            print(json.dumps({"result": []}))
    except Exception as exc:
        # Never crash Flow: surface the error as a single result instead.
        if method in ("query", "context_menu"):
            print(json.dumps({"result": [{
                "Title": "VSCode Workspaces plugin error",
                "SubTitle": "%s: %s" % (type(exc).__name__, exc),
                "IcoPath": ICON_APP,
                "JsonRPCAction": {"method": "noop", "parameters": []},
            }]}))


if __name__ == "__main__":
    main()
