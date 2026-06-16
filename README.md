# VSCode Recent — Flow Launcher 插件

用 `{` 列出并打开最近的 VS Code 文件夹/工作区。

## 为什么有这个插件
2026 年起的新版 VS Code 不再把"最近打开"写进 `state.vscdb` 的
`history.recentlyOpenedPathsList` 键(旧的 C#/PowerToys VSCodeWorkspaces 插件全靠它,
于是失效:输入 `{` 没有任何结果)。本插件改读**当前真正的数据源**
`%APPDATA%\Code\User\globalStorage\storage.json` 里的
`profileAssociations` / `backupWorkspaces` / `windowsState`,
并保留对旧版 `state.vscdb` 键的兼容回退。

## 特性
- 纯标准库,**零第三方依赖**(不会再出现 `ModuleNotFoundError`)
- 输出 ASCII 转义 JSON,中文路径(简历/毕业论文…)绝不因编码崩溃
- 按"最近打开时间"排序(读 `workspaceStorage/*/workspace.json` 的 mtime)
- 自动跳过已删除的本地文件夹
- 支持 `file://` 本地、`vscode-remote://`(WSL/SSH/Dev Container/Codespaces)
- 多编辑器:`Code` / `Code - Insiders` / `VSCodium`(在 `main.py` 的 `EDITORS` 里加)
- `Shift+Enter` 右键菜单:新窗口打开 / 在资源管理器中显示 / 复制路径
- 任何异常都以一条结果项呈现,不让 Flow 崩溃(FATAL)

## 文件
- `main.py` — 全部逻辑(JSON-RPC、读取、解析、动作)
- `plugin.json` — Flow 元数据(`Language: python`,关键字 `{`)
- `Images/` — 图标
- `.github/workflows/Publish Release.yml` — push 到 main 自动打 tag + 发布 release zip
- `requirements.txt` — 空(纯标准库;仅为让 CI 的 pip 步骤通过)
- `store-manifest-entry.json` — 提交到插件市场用的清单条目

## 部署(本地)
复制到 Flow 的插件目录后**完全重启 Flow**:
```
D:\Scoop\persist\Flow-Launcher\UserData\Plugins\VSCodeRecent\
```
(本仓库即源码;改完同步过去再重启 Flow 即可。)

## 发布到插件市场
仓库:`https://github.com/xt-fg/Flow.Launcher.Plugin.VSCodeRecent`
1. push 本目录到该仓库,GitHub Actions 自动出 release(tag `v<Version>`)。
2. Fork [Flow.Launcher.PluginsManifest](https://github.com/Flow-Launcher/Flow.Launcher.PluginsManifest),
   把 `store-manifest-entry.json` 放到其 `plugins/` 目录(命名
   `VSCodeRecent-cee1cdb5-07b3-495d-8c16-636035ab3a51.json`),提 PR。
3. 合并 + CDN 同步后即可在商店 `pm install`。期间可用
   `pm install <release zip url>` 直接安装。

## 开发/测试(在 WSL 上)
```bash
APPDATA=/mnt/c/Users/<你>/AppData/Roaming VSCWS_DRIVE_MAP=/mnt \
  python3 main.py '{"method":"query","parameters":[""]}'
```
`VSCWS_DRIVE_MAP` 只是测试钩子:把 `D:\x` 映射到 `/mnt/d/x` 做存在性检查;
Windows 上不设此变量,自动无效。
