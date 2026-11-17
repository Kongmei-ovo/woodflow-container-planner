# 木序 · 智能排柜工作台

本地运行的中文排柜工具：导入客户订单，核对产品、工厂和数量，按工厂分柜，输出排柜 Excel。产品资料、原始订单、调整记录、历史方案和备份均保存在电脑本机，不依赖外部 AI 服务。

[下载版本](https://github.com/Kongmei-ovo/woodflow-container-planner/releases) · [构建状态](https://github.com/Kongmei-ovo/woodflow-container-planner/actions) · [反馈问题](https://github.com/Kongmei-ovo/woodflow-container-planner/issues) · [版本记录](CHANGELOG.md)

## 给使用者

在 **Releases** 中下载适合电脑的 ZIP；`Source code` 是源码，不是安装包。

| 电脑 | 下载包 |
| --- | --- |
| Windows 10/11，Intel/AMD 64 位 | `WoodFlow-版本-Windows64.zip` |
| Mac，Apple Silicon | `WoodFlow-版本-macOS-arm64.zip` |
| Mac，Intel | `WoodFlow-版本-macOS-x64.zip` |

完整解压后，Windows 双击“启动排柜工具.bat”，Mac 双击 `WoodFlow.app`。程序自带 Python 和依赖，无需另行安装开发环境。Windows ARM 和 32 位系统不在支持范围内。

ZIP 内含说明书 PDF、离线 HTML、规则说明和反馈记录。首次使用可点击“先用练习示例体验”；练习数据均为虚构。Windows 启动有问题时运行包内“遇到问题请运行自检.bat”。各版本实际验证范围请以 Release 说明和对应 Actions 记录为准。

“我的排柜”以订单列表打开，支持搜索订单名称、客户和备注，按状态、工厂、目的仓、创建日期筛选。可编辑订单信息、进入明细审核；删除先移入回收站，支持恢复原订单及方案。

## 日常流程

1. **资料设置**：先导入产品编码、名称、单件 CBM 和毛重，再导入工厂产品表；工厂可按工作表名称识别。价格表可选。
2. **我的排柜 → 新增订单**：导入 `.xlsx` 或 `.csv` 客户订单，核对工作表、表头和字段。支持四仓横表（含 `DCSYD QTY` 等标准表头）及“目的仓＋数量”长表。同表并列件数和 CBM 时按表头分组区分；重复仓名的单位不明确时需要手动确认。
3. **处理问题**：界面解释每行为什么需要确认、应该填什么。核实产品绑定、工厂、计量和交期；可以筛选有数量调整的行。
4. **排柜并导出**：生成方案，按工厂查看，调整或锁柜后另存版本，导出 Excel。

不根据相似名称自动采用产品；供应商名称不等同于生产工厂。多包装产品须使用审核确认的整件 CBM 和毛重，不把净重当毛重。

## 排柜与数量规则

不同工厂、目的仓、明确发货批次分别排柜，NEW 新品与常规品分开。

| 柜型 | 体积上限 | 毛重上限 |
| --- | ---: | ---: |
| 20GP | 28 m³ | 22,800 kg |
| 40GP | 58 m³ | 22,800 kg |
| 40HQ | 68 m³ | 22,800 kg |

优化依次考虑柜数、同款拆柜次数、ABC 等级混装、柜型总体积。计算预算到期时返回已校验的可行方案；只有各阶段都证明最优时才显示“已证明最优”。工具计算件数、体积和毛重分配，不计算实物位置、堆叠和承重。

导入时默认启用下列已确认规则，也可在界面调整处理方式：

- 空白仓数量视为 0；无法识别的文字数量仍需要审核。
- 正数订单向上凑至 5 的倍数。每款跨四仓合计自动增加最多 30 件，不足 100 件时在此上限内尽量补足。
- 只向原本有订单的仓补量，按原下单比例分配。例：49 件补至 75 件，80 件补至 100 件。仍不足 100 件时提示，允许继续排柜。
- 原数量不变，记录调整数量、差额和原因；有改量时导出附“数量调整”工作表。
- 可以先排柜后按柜补 LSD，再另存新版本。已有明确日期不被覆盖；原订单多个日期未拆分数量时仍需确认。文件名不用于猜测交期。

## 保存和更新

产品、订单、已保存方案和导出记录在本机留存，方案保存当时的产品与订单快照。关闭浏览器不会清空资料；停止服务请点击“退出工具”。

重要工作后到“历史与备份”下载完整 ZIP 备份，包含数据库、原订单和导出文件。换电脑可恢复；恢复会替换当前资料并保留恢复前的数据目录。

| 系统 | 默认数据目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\WoodFlow\ContainerPlanner` |
| macOS | `~/Library/Application Support/ContainerPlanner` |

实际位置在界面中显示。更新前先保存调整并备份，再把新包解压到新目录，用同一电脑账户启动。新版会等待旧版计算完成并正常关闭旧版，接管同一份资料；重复打开同版或误开较旧版时复用已运行的新版。此功能不自动联网下载安装更新。公开仓库和下载包不包含真实客户订单、产品表、数据库或备份。

## 本地开发

需要 Python 3.11、Node.js 22。安装依赖并运行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python -m pytest -q
.venv/bin/python run_planner.py
```

Windows 将 `.venv/bin/python` 替换为 `.venv\Scripts\python.exe`。本地 API 仅监听 `127.0.0.1`，跨站写入会被拒绝。开发时使用 `--data-dir .local-data/dev --no-browser`，避免改动日常业务资料。前端开发命令为 `npm --prefix frontend run dev`，后端端口对应 `--port 8765`。

浏览器验收使用临时空目录和虚构 Excel，不读取已有业务数据：

```sh
npx --prefix frontend playwright install chromium
.venv/bin/python scripts/browser_acceptance.py
.venv/bin/python -m container_planner.selfcheck --output .local-data/selfcheck.txt
```

## 构建与发布

安装包和交付说明书统一由 GitHub Actions 云端生成，使用公开仓库的标准托管运行器。通过 Release 链接交付，不提供本地构建包；云端失败时修复并重跑。

- 每次推送 `main` 或提交 PR，自动运行测试、浏览器完整流程并构建说明书。
- 推送与代码版本一致的 `v*` 标签，自动构建 Windows、Apple Silicon Mac、Intel Mac 包，在各原生平台验证后发布 Release。
- 任何平台失败都不发布下载包；带 `-beta` 等后缀的版本发布为预发行版。
- 可在 Actions 手动触发完整构建，下载临时构建产物。

详见 [发布步骤](docs/RELEASING.md)。版本来源为 `container_planner/__init__.py`，前端 `package.json` 和锁文件须保持一致，CI 会校验标签。说明书源文件为 `scripts/create_trial_guide.py`，截图在 `docs/assets`，自动生成 PDF 和离线 HTML。

源码目录：`container_planner/` 后端与算法，`frontend/` 中文工作台，`tests/` 自动化测试，`scripts/` 构建和验收，`.github/workflows/build.yml` 持续集成与发布。
