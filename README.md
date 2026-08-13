# XHS Comment Cleaner

[![Build Windows EXE](https://github.com/feizhanxia/xhs-comment-cleaner/actions/workflows/build-windows.yml/badge.svg)](https://github.com/feizhanxia/xhs-comment-cleaner/actions/workflows/build-windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个用于验证“小红书历史评论本地清理”可行性的 Windows 开源项目。它使用系统自带的 Microsoft Edge，并坚持只在能够确认评论 ID、作者和原笔记时执行删除。

```text
双击 EXE → 人工登录小红书 → 验证网页能力
```

不需要安装 Python、Node.js、Playwright 浏览器或 Chrome；不需要命令行、云服务器、账号系统或管理员权限。

> [!CAUTION]
> 当前已确认的主要限制是：小红书普通 Edge 网页版没有经过验证的“我发出的全部评论”入口，因此本项目当前**不能自动枚举账号全部历史评论，也不能完成最初承诺的一键清理目标**。程序会拒绝在首页或任意笔记页扫描，不再用“0 条”掩盖入口缺失。请勿把当前版本用于正式批量删除。

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
- 浏览器自动化使用异步 Playwright，并固定在一个长期运行的专用 asyncio 线程；Windows 强制使用 Proactor event loop，避免同步 greenlet 桥与 GUI 线程模型冲突。

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

## 当前可行性结论

1. 普通网页版能打开笔记和评论区，但未发现集中展示当前账号“发出的全部评论”的可靠入口。
2. “消息 / 评论和 @”主要是收到的互动，不能据此证明覆盖自己主动发出的全部评论。
3. 没有历史评论清单，就无法得到每条评论所属笔记的 URL 与评论 ID；只滚动首页无法扫描历史评论。
4. 直接构造未公开接口、读取手机 App 私有流量或绕过平台限制，不符合本项目的安全约束，也无法作为稳定开源方案。
5. 后续只有在小红书提供官方历史列表、官方数据导出包含可定位字段，或用户合法提供一份原笔记链接清单时，才能继续验证逐条定位和删除流程。

程序仍保留扫描和删除代码用于研究，但扫描前必须识别明确的“我发出的评论”页面；否则会停止并说明原因。

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

GitHub Actions 会在 `windows-latest` 上用 Python 3.12 运行测试、构建、启动 GUI smoke test，并从打包后的 EXE 内实际启动异步 Playwright + 系统 Edge。全部通过后才上传 EXE；推送 `v*` 标签时会自动创建带 EXE 和校验文件的 GitHub Release。

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

- 当前普通网页版未发现可验证的“我发出的全部评论”入口，核心自动枚举目标尚不可实现。
- 扫描仅在明确看到“没有更多了/已经到底了”时标记完整，否则界面会明确提示覆盖范围不确定。
- 当前网页若不暴露稳定 comment ID 或可靠作者 ID，程序会安全停止，不能删除。

## 参与贡献与安全报告

开发约束见 [CONTRIBUTING.md](CONTRIBUTING.md)。请勿在公开 Issue 中粘贴 Cookie、Token 或账号数据；安全问题请按 [SECURITY.md](SECURITY.md) 提交。

## License

[MIT](LICENSE)
