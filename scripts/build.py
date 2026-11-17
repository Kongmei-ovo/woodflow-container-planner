"""Build on the target OS/architecture; does not upload or publish anything."""
import os
import platform
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__":
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "WoodFlow",
               "--onedir", "--windowed", "--add-data", f"{ROOT / 'frontend' / 'dist'}{os.pathsep}frontend",
               "--collect-submodules", "ortools.sat.python", "--collect-data", "ortools",
               "--collect-data", "certifi",
               "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.auto",
               "--hidden-import", "uvicorn.protocols.http.auto", "--hidden-import", "uvicorn.lifespan.on"]
    if sys.platform == "darwin":
        command += ["--osx-bundle-identifier", "local.woodflow.containerplanner"]
    command += [str(ROOT / "run_planner.py")]
    subprocess.run(command, cwd=ROOT, check=True)
    archive = ROOT / "dist" / f"WoodFlow-{sys.platform}-{platform.machine()}.zip"
    if sys.platform == "darwin":
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(ROOT / "dist" / "WoodFlow.app"), str(archive)], check=True)
    else:
        shutil.make_archive(str(archive.with_suffix("")), "zip", ROOT / "dist", "WoodFlow")
    print(f"已构建：{ROOT / 'dist'} ({sys.platform}/{platform.machine()})")
