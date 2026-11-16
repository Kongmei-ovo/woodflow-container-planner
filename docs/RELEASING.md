# 更新与发布

仓库：https://github.com/Kongmei-ovo/woodflow-container-planner

## 平时更新

代码修改和说明书修改提交到 `main`；Actions 自动检查。朋友的问题可以记录到 Issues，附程序版本、电脑系统、操作步骤、期望结果和实际提示。截图和附件请自行去除不需要公开的业务资料。

只更新说明书可以直接提交，不必改程序版本。需要把新说明书和程序作为一个下载版本交付时，发布一个新版本号，旧 Release 保留原样。

## 发布新版本

1. 修改 `container_planner/__init__.py` 的 `__version__`，同步 `frontend/package.json`、`frontend/package-lock.json` 顶层和根包版本。
2. 更新 `CHANGELOG.md` 和 `docs/RELEASE_NOTES.md`。规则变化同步修改 `docs/release/本版规则说明.txt`；说明书文字在 `scripts/create_trial_guide.py`，截图在 `docs/assets`。
3. 运行测试并提交。示例：

```sh
python scripts/release_files.py
python -m pytest -q
npm --prefix frontend run build
git add <本次修改的文件>
git commit -m "Release 1.1.0-beta.3"
git push origin main
git tag -a v1.1.0-beta.3 -m "木序排柜 1.1.0-beta.3"
git push origin v1.1.0-beta.3
```

4. 在 Actions 查看标签构建。CI 检查版本一致性，执行自动化测试、浏览器流程，生成 PDF/HTML，分别构建 Windows64、macOS-arm64、macOS-x64。
5. Windows 在嵌入运行时中验证中文路径、启动、浏览器流程、备份恢复、重启、排柜和导出。两种 Mac 架构分别验证独立应用的启动、后台排柜和导出。
6. 所有平台通过后才创建 Release，上传三个 ZIP、各自 SHA256、PDF 和 HTML。版本号含后缀时标记为预发行版。

发布后不要移动旧标签或覆盖旧安装包。需要修正已发布内容时增加新版本号。构建失败时先修复原因；未发布的失败标签可以在 Actions 中重新运行，但该标签对应源码必须与准备发布的版本一致。

## 手动构建

Actions 的“Test, build and release”提供 Run workflow。选 `main` 会构建并保留产物，不会自动创建 Release。只有版本标签会进入正式发布步骤。

Windows 便携包可在 Mac 上组装，但这不等于 Windows 原生验收。`scripts/assemble_trial.py --windows-tested` 仅供完成 Windows 验收后的 Windows 构建机使用。

## 公开内容范围

提交源码、生成器、依赖锁文件、虚构测试和已确认无业务内容的说明书截图。客户 Excel、数据库、备份、日志、本地数据目录、私人确认单、真实订单验收脚本和构建产物均排除。下载包由白名单目录组装，业务数据位于用户目录，不随程序分发。
