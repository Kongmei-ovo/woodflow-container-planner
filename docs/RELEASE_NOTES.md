请下载与你电脑匹配的 ZIP，**Source code 不是可直接启动的程序包**。

- Windows 10/11 Intel/AMD 64 位：`Windows64.zip`；完整解压后双击“启动排柜工具.bat”。
- Apple Silicon Mac：`macOS-arm64.zip`；解压后打开 WoodFlow.app。
- Intel Mac：`macOS-x64.zip`；解压后打开 WoodFlow.app。

程序自带运行环境，无需安装 Python 或 Node。包内包含离线说明书、规则说明和反馈记录；也可单独下载 PDF/HTML。

本版修正订单导入：支持两行及合并表头，同仓名并列时区分件数与CBM体积；单位不清的重复列需手动确认。选到产品资料表会提前提示，修改表头会重新识别列。

原有5件凑整、每款自动增量最多30件、NEW独立分柜、ABC偏好和后补LSD保持可用。更新前先备份，退出旧版再启动新版。曾用旧版导入并列CBM的订单，请重新导入核对原订件数。

发布前已在对应 Windows、Apple Silicon Mac 和 Intel Mac 构建机完成自动验收；详细结果见对应标签的 Actions 记录。Windows 包附自检工具，便于检查使用者电脑的运行环境。

更新前先到“历史与备份”下载完整备份，在旧版点击“退出工具”，再把新版解压到新目录启动。业务资料保存在用户目录，安装包不含客户资料。
