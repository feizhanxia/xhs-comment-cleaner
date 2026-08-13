# XHS Comment Cleaner

[![Build Windows EXE](https://github.com/feizhanxia/xhs-comment-cleaner/actions/workflows/build-windows.yml/badge.svg)](https://github.com/feizhanxia/xhs-comment-cleaner/actions/workflows/build-windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一款面向普通用户的 Windows 本地工具：使用系统自带的 Microsoft Edge，扫描当前小红书账号能够发现的历史评论和回复，并在多重确认后逐条删除。

```text
双击 EXE → 人工登录小红书 → 扫描 → 确认 → 逐条删除
```

不需要安装 Python、Node.js、Playwright 浏览器或 Chrome；不需要命令行、云服务器、账号系统或管理员权限。

> [!CAUTION]
> 删除操作通常无法恢复。当前项目仍处于测试阶段，请先使用专门测试账号和少量测试评论验证。项目只能处理网页端本次扫描能够发现、且能确认属于当前账号的记录，不承诺覆盖账号 100% 的历史评论。小红书页面变化也可能使扫描或删除安全停止。

## 下载 Windows EXE

- 稳定版本：从 [GitHub Releases](https://github.com/feizhanxia/xhs-comment-cleaner/releases) 下载 `XHSCommentCleaner.exe`。
- 最新构建：打开 [Build Windows EXE](https://github.com/feizhanxia/xhs-comment-cleaner/actions/workflows/build-windows.yml)，在最新成功运行的 Artifacts 中下载。
- 校验文件：同一构建提供 `XHSCommentCleaner.exe.sha256`。

当前 EXE 没有商业代码签名证书，Windows SmartScreen 可能显示“未知发布者”。请只从本仓库的 Release 或 Actions 下载，并核对 SHA-256。

## 安全设计

- 使用 `%LOCALAPPDATA%\XHSCommentCleaner\profile\`，不接触用户日常 Edge profile。
- 扫描阶段只观察正常网页已渲染的内容和已产生的 JSON response，不自行高频调用私有 API。
- 删除前同时核对扫描账号、记录作者 ID、页面作者链接和评论 ID。
- 点击后刷新页面，只有目标评论 ID 已不存在才记录为删除成功。
- 无法确认身份、页面结构或目标评论时停止或跳过，宁可漏删，不误删。
- 遇到验证码、访问频繁、账号异常或登录失效时暂停，等待用户人工处理。
- SQLite 持久化每条结果，程序中断后可从待处理记录继续。
- `app.log` 记录每次启动和关键操作；`crash.log` 保留无控制台 EXE 的未捕获异常，便于定位现场问题。

## 开发环境

- Windows 11
- Python 3.12
- 已安装 Microsoft Edge

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m app.main
```

不要运行 `playwright install`。程序通过 `channel="msedge"` 启动系统 Edge，不携带 Chromium、Firefox 或 WebKit。

## 调试与真实页面校准

1. 运行程序，点击“打开小红书 / 登录”，人工完成登录。
2. 在程序打开的独立 Edge 中进入能够看到“我发表的评论/互动记录”的页面。
3. 回到程序，检查登录状态，然后点击“扫描当前评论记录页”。
4. 扫描器只观察正常页面已经产生的 JSON response，并只保存 `author_id == current_user_id` 的记录；DOM fallback 只接受带稳定评论 ID 的容器。
5. 用专门的测试账号和可恢复的测试评论完成单条删除 PoC。根据真实快照修改 `app/xhs/selectors.py`，不得添加坐标点击或位置型 selector。
6. 验证目标评论 ID 刷新后不存在，再进行 10 条评论、异常 selector、登录失效和风控测试。

设置 `XHS_CLEANER_DEBUG=1` 可在开发环境开启控制台日志。异常截图和日志位于 `%LOCALAPPDATA%\XHSCommentCleaner\`。

## 测试

```bat
python -m unittest discover -s tests -v
```

现有自动化测试覆盖 SQLite 去重、断点状态、三次重试和删除前的所有权/域名安全门。真实 Edge、小红书登录、扫描完整性、删除与 Windows 干净机测试必须人工执行。

## 构建

双击 `build.bat`。脚本会创建 Python 3.12 虚拟环境、安装构建依赖、运行测试，先构建并 smoke-test onedir，再生成 onefile：

```text
dist\XHSCommentCleaner.exe
```

PyInstaller spec 使用 windowed onefile，并收集 Playwright Python 驱动，但不会下载或打包浏览器。正式发布前应先另做 onedir 干净机验证；若 onefile 在目标机不稳定，应改用 onedir runtime 启动器方案，用户数据目录不能随 runtime 更新而删除。

GitHub Actions 会在 `windows-latest` 上用 Python 3.12 运行测试、构建、启动 smoke test，并上传 EXE。推送 `v*` 标签时会自动创建带 EXE 和校验文件的 GitHub Release。

## 用户数据

```text
%LOCALAPPDATA%\XHSCommentCleaner\
  profile\       独立 Edge 登录环境
  data\data.db   扫描与删除进度
  logs\app.log
  screenshots\
  runtime\
```

程序不读取或保存密码，不处理验证码，不使用默认 Edge profile，不终止用户自己的 Edge，也不申请管理员权限。

## 已知限制

- 尚未使用真实小红书测试账号验证当前页面入口、网络字段和 selector。
- 扫描仅在明确看到“没有更多了/已经到底了”时标记完整，否则界面会明确提示覆盖范围不确定。
- 当前网页若不暴露稳定 comment ID 或可靠作者 ID，程序会安全停止，不能删除。

## 参与贡献与安全报告

开发约束见 [CONTRIBUTING.md](CONTRIBUTING.md)。请勿在公开 Issue 中粘贴 Cookie、Token 或账号数据；安全问题请按 [SECURITY.md](SECURITY.md) 提交。

## License

[MIT](LICENSE)
