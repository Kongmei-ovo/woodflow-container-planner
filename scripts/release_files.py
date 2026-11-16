"""Check version consistency and collect only explicitly named release files."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from container_planner import __version__


def check(tag=None):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?", __version__):
        raise ValueError("版本号格式无效")
    for name in ["package.json", "package-lock.json"]:
        data=json.loads((ROOT/"frontend"/name).read_text())
        assert data["version"] == __version__, name
        if name == "package-lock.json":
            assert data["packages"][""]["version"] == __version__, name
    if tag:
        assert tag == "v"+__version__, "Tag须与程序及前端版本一致"
    return __version__


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--collect",choices=["windows", "macos-arm64", "macos-x64"])
    args=parser.parse_args()
    version=check(args.tag)
    if args.collect:
        label={"windows":"Windows64","macos-arm64":"macOS-arm64","macos-x64":"macOS-x64"}[args.collect]
        source=ROOT/"dist/交付版"/f"木序排柜_{version}_{label}.zip"
        out=ROOT/"dist/releases";out.mkdir(parents=True,exist_ok=True)
        name=f"WoodFlow-{version}-{label}.zip"
        shutil.copy2(source,out/name)
        (out/(name+".sha256.txt")).write_text(f"{hashlib.sha256(source.read_bytes()).hexdigest()}  {name}\n",encoding="utf-8")
    print(version)
