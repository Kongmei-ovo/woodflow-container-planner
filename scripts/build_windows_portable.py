"""Assemble official Windows binaries without pretending to cross-compile PyInstaller.

The result includes CPython's embeddable distribution and platform-specific PyPI
wheels. Assembly can run on macOS; running acceptance tests still requires Windows.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from email import message_from_bytes
from pathlib import Path
from zipfile import ZipFile
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
PYTHON_VERSION = "3.13.17"


def target_environment():
    return {**default_environment(), "sys_platform": "win32", "os_name": "nt", "platform_system": "Windows",
            "platform_machine": "AMD64", "python_version": "3.13", "python_full_version": PYTHON_VERSION,
            "platform_python_implementation": "CPython", "implementation_name": "cpython", "extra": ""}


def target_requirements():
    selected = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate(target_environment()):
            continue
        requirement.marker = None
        selected.append(str(requirement))
    return selected


def build(download=True):
    if not (ROOT / "frontend/dist/index.html").exists():
        raise ValueError("请先构建前端。")
    cache = ROOT / ".local-data" / "windows-wheels"
    cache.mkdir(parents=True, exist_ok=True)
    if download:
        # Resolve into an empty directory so an older wheel cannot be mixed into
        # the same runtime after a dependency publishes an update.
        with tempfile.TemporaryDirectory(prefix="resolved-windows-wheels-", dir=cache.parent) as resolved:
            subprocess.run([sys.executable, "-m", "pip", "download", *target_requirements(),
                            "colorama", "tzdata", "--dest", resolved, "--platform", "win_amd64", "--python-version", "313",
                            "--implementation", "cp", "--abi", "cp313", "--only-binary=:all:"], check=True)
            shutil.rmtree(cache)
            shutil.copytree(resolved, cache)
    embedded = ROOT / ".local-data" / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{embedded.name}"
    if not embedded.exists():
        urllib.request.urlretrieve(url, embedded)
    package = ROOT / "dist" / "WoodFlow-Windows-x64"
    if package.exists():
        shutil.rmtree(package)
    runtime = package / "runtime"
    runtime.mkdir(parents=True)
    with ZipFile(embedded) as archive:
        archive.extractall(runtime)
    site = runtime / "Lib/site-packages"
    site.mkdir(parents=True)
    manifest = {"python": PYTHON_VERSION, "python_source": url,
                "python_sha256": hashlib.sha256(embedded.read_bytes()).hexdigest(), "wheels": []}
    distributions = {}
    for wheel in sorted(cache.glob("*.whl")):
        if not wheel.name.endswith(("win_amd64.whl", "any.whl")):
            raise ValueError(f"非Windows依赖：{wheel.name}")
        with ZipFile(wheel) as archive:
            metadata_path = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            metadata = message_from_bytes(archive.read(metadata_path))
            if canonicalize_name(metadata["Name"]) in distributions:
                raise ValueError(f"依赖存在重复版本，请重新下载：{metadata['Name']}")
            distributions[canonicalize_name(metadata["Name"])] = metadata
            for name in archive.namelist():
                if name.endswith("/"):
                    continue
                parts = Path(name).parts
                if any(p in {".", ".."} for p in parts) or name.startswith("/"):
                    raise ValueError("Wheel路径无效")
                if len(parts) >= 3 and parts[0].endswith(".data") and parts[1] in {"purelib", "platlib"}:
                    target = site.joinpath(*parts[2:])
                elif len(parts) >= 3 and parts[0].startswith("msvc_runtime-") and parts[1] == "data" and parts[-1].endswith(".dll"):
                    # C++ dependencies must also work on PCs without a prior VC++ install.
                    # The wheel ships copies for both sys.prefix and Scripts. Both
                    # resolve beside python.exe in this embeddable distribution.
                    target = runtime / parts[-1]
                elif len(parts) >= 2 and parts[0].endswith(".data"):
                    continue  # optional console scripts/headers aren't application dependencies
                else:
                    target = site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        manifest["wheels"].append({"filename": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()})
    environment = target_environment()
    for metadata in distributions.values():
        if metadata.get("Requires-Python") and PYTHON_VERSION not in SpecifierSet(metadata["Requires-Python"]):
            raise ValueError(f"Python版本不兼容：{metadata['Name']}")
        for raw in metadata.get_all("Requires-Dist", []):
            req = Requirement(raw)
            if req.marker and not req.marker.evaluate(environment):
                continue
            installed = distributions.get(canonicalize_name(req.name))
            if not installed or installed["Version"] not in req.specifier:
                raise ValueError(f"Windows依赖未满足：{metadata['Name']} -> {req}")
    (runtime / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n../app\nimport site\n")
    app = package / "app"
    app.mkdir()
    shutil.copytree(ROOT / "container_planner", app / "container_planner", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "run_planner.py", app / "run_planner.py")
    shutil.copytree(ROOT / "frontend/dist", app / "frontend/dist")
    shutil.copy2(ROOT / "README.md", package / "README.md")
    (package / "WoodFlow.bat").write_text('@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n'
        'if not exist "runtime\\pythonw.exe" goto missing\r\nif not exist "app\\run_planner.py" goto missing\r\n'
        'if not exist "app\\frontend\\dist\\index.html" goto missing\r\n'
        'start "" "%~dp0runtime\\pythonw.exe" "%~dp0app\\run_planner.py"\r\nexit /b 0\r\n'
        ':missing\r\necho 请先右键ZIP选择全部解压，并保留runtime和app文件夹。\r\npause\r\nexit /b 1\r\n', encoding="utf-8", newline="")
    (package / "启动排柜工具.bat").write_bytes((package / "WoodFlow.bat").read_bytes())
    (package / "遇到问题请运行自检.bat").write_text('@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n'
        'echo 木序运行环境自检：使用虚构数据，不修改真实订单。\r\n'
        '"%~dp0runtime\\python.exe" -m container_planner.selfcheck\r\n'
        'echo.\r\necho 请将上面的结果截图，或发送提示位置的自检结果.txt。\r\npause\r\n', encoding="utf-8", newline="")
    (package / "启动说明.txt").write_text("木序 · Windows便携版\n\n请先解压整个ZIP，双击 WoodFlow.bat 或 启动排柜工具.bat。\n无需另行安装Python或Node。不要单独移动runtime或app文件夹。\n\n本包在Mac上组装，尚未在真实Windows系统运行验收。\n原始业务资料不包含在安装包中。在‘历史与备份’恢复备份即可迁移资料。\n", encoding="utf-8-sig")
    (package / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2))
    required = [runtime / "pythonw.exe", runtime / "python313.dll", site / "ortools/sat/python/cp_model.py",
                site / "fastapi/__init__.py", app / "frontend/dist/index.html", runtime / "msvcp140.dll",
                runtime / "vcruntime140.dll", runtime / "vcruntime140_1.dll"]
    if not all(p.is_file() for p in required) or not list(site.glob("ortools/sat/python/*.pyd")):
        raise ValueError("Windows运行时不完整。")
    archive = shutil.make_archive(str(package), "zip", package.parent, package.name)
    print(f"已组装Windows x64便携包（未运行验证）：{archive}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-download", action="store_true")
    build(not parser.parse_args().no_download)
