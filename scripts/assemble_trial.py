"""Assemble friend-facing downloads; business data never enters release staging."""
import argparse
from datetime import date
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from container_planner import __version__ as VERSION


def assemble(target_platform="windows", windows_tested=False):
    if windows_tested and sys.platform != "win32":
        raise ValueError("Windows验收标记只能在Windows构建机上使用。")
    architecture = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    label = "Windows64" if target_platform == "windows" else f"macOS-{architecture}"
    target = ROOT / "dist/交付版" / f"木序排柜_{VERSION}_{label}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    if target_platform == "windows":
        source = ROOT / "dist/WoodFlow-Windows-x64"
        for folder in ("app", "runtime"):
            shutil.copytree(source / folder, target / folder)
        for name in ("启动排柜工具.bat", "遇到问题请运行自检.bat"):
            shutil.copy2(source / name, target / name)
        info = target / "技术信息"
        info.mkdir()
        shutil.copy2(source / "runtime-manifest.json", info / "运行时清单.json")
        status = ("已在Windows构建机运行：独立运行时、中文和空格路径、浏览器工作流、备份恢复、重启及Excel导出。"
                  if windows_tested else "尚未在Windows原生机器运行验收。首次请运行包内自检，并确认练习Excel能导出。")
    else:
        if sys.platform != "darwin":
            raise ValueError("macOS包须在Mac上构建。")
        subprocess.run(["ditto", str(ROOT / "dist/WoodFlow.app"), str(target / "WoodFlow.app")], check=True)
        status = "本架构独立运行包的启动、后台排柜和Excel导出检查已通过，详见对应GitHub Actions运行记录。"
    for name in ("开始使用.txt", "使用指南.html", "反馈记录.txt", "本版规则说明.txt"):
        shutil.copy2(ROOT / "docs/release" / name, target / name)
    pdf = ROOT / "docs/release/使用指南.pdf"
    if not pdf.exists():
        pdf = ROOT / "output/pdf/木序排柜试用指南.pdf"
    shutil.copy2(pdf, target / "使用指南.pdf")
    if target_platform == "macos":
        (target / "开始使用.txt").write_text(f"木序排柜 {VERSION} macOS {architecture}\n\n完整解压后双击WoodFlow.app，无需安装Python或Node。\n请使用与你的CPU匹配的下载包。说明书中的业务步骤同样适用。\n首次打开若被系统阻止，请核对来源后在系统设置的隐私与安全性中处理。\n更新前先备份并退出旧版；数据保存在用户目录，不在应用包内。\n", encoding="utf-8")
    (target / "版本与测试说明.txt").write_text(f"木序排柜朋友试用版\n版本：{VERSION}\n构建日期：{date.today().isoformat()}\n平台：{label}\n\n{status}\n\n程序自带运行环境，业务资料保存在本机。包内练习数据均为虚构，不含客户订单和数据库。\n本版规则见 本版规则说明.txt。操作步骤见 使用指南.pdf 或 使用指南.html。\n请在历史与备份页面定期备份；更新前退出旧版，并解压到新目录。\n", encoding="utf-8-sig")
    if target_platform == "macos":
        archive = Path(str(target) + ".zip")
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(target), str(archive)], check=True)
    else:
        archive = Path(shutil.make_archive(str(target), "zip", target.parent, target.name))
    with ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        # ditto writes UTF-8 names without ZIP's UTF-8 flag. Finder decodes them,
        # whereas Python defaults to CP437; normalize for cross-platform auditing.
        names = []
        for entry in zipped.infolist():
            name = entry.filename
            if not entry.flag_bits & 0x800:
                try:
                    name = name.encode("cp437").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            names.append(name)
        assert any(n.endswith("/使用指南.pdf") for n in names)
        assert not any(n.lower().endswith((".xlsx", ".sqlite3", ".db")) for n in names)
    archive.with_suffix(".sha256.txt").write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")
    print(archive)
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["windows", "macos"], default="windows")
    parser.add_argument("--windows-tested", action="store_true")
    args = parser.parse_args()
    assemble(args.platform, args.windows_tested)
