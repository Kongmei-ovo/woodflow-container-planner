"""Run real Windows acceptance against the supplied portable runtime, not host Python."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from container_planner import __version__

if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("此验收必须在Windows中执行")
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="木序 试用验收-") as temp:
        temp = Path(temp)
        package = temp / "中文 解压路径" / "WoodFlow"
        shutil.copytree(root / "dist/WoodFlow-Windows-x64", package)
        subprocess.run([sys.executable, "scripts/smoke_package.py", "--windows-portable", "--package-root", str(package)], cwd=root, check=True)
        data = temp / "我的 订单资料"
        process = subprocess.Popen([str(package / "runtime/python.exe"), str(package / "app/run_planner.py"),
                                    "--data-dir", str(data), "--no-browser"], cwd=package)
        client = None
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError(f"启动失败: {process.returncode}")
                try:
                    url = json.loads((data / "instance.json").read_text())["url"]
                    client = httpx.Client(base_url=url, trust_env=False, timeout=20)
                    if client.get("/api/health").json()["ok"]:
                        break
                except (OSError, ValueError, httpx.HTTPError):
                    if client: client.close()
                    client = None
                    time.sleep(.2)
            if client is None:
                raise RuntimeError("启动超时")
            # A second double-click must reuse the first instance, including when proxy env is set.
            env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}
            subprocess.run([str(package / "runtime/python.exe"), str(package / "app/run_planner.py"),
                            "--data-dir", str(data), "--no-browser"], env=env, check=True, timeout=15)
            empty_backup = client.get("/api/backup").content
            restored = client.post("/api/restore", files={"file": ("empty-backup.zip", empty_backup)})
            assert restored.status_code == 200, f"恢复空资料备份失败：{restored.status_code} {restored.text}"
            subprocess.run([sys.executable, "-m", "scripts.browser_fixtures"], cwd=root, check=True)
            subprocess.run(["node", "scripts/e2e.cjs"], cwd=root, env={**os.environ, "PLANNER_TEST_URL": url}, check=True)
            subprocess.run(["node", "scripts/e2e_import.cjs"], cwd=root, env={**os.environ, "PLANNER_TEST_URL": url}, check=True)
            # Restart from saved records and re-export the prior plan.
            state = client.get("/api/bootstrap").json()
            plans = state["plans"]
            assert plans and state["version"] == __version__
            backup = client.get("/api/backup").content
            assert backup.startswith(b"PK")
            response = client.post("/api/restore", files={"file": ("backup.zip", backup)})
            assert response.status_code == 200, f"恢复备份失败：{response.status_code} {response.text}"
            for _ in range(50):
                if client.post("/api/shutdown").status_code == 200: break
                time.sleep(.1)
            process.wait(timeout=15)
            process = subprocess.Popen([str(package / "runtime/python.exe"), str(package / "app/run_planner.py"),
                                        "--data-dir", str(data), "--no-browser"], cwd=package)
            client.close(); client = None
            for _ in range(150):
                try:
                    url = json.loads((data / "instance.json").read_text())["url"]
                    client = httpx.Client(base_url=url, trust_env=False, timeout=20)
                    if client.get("/api/health").json()["ok"]: break
                except (OSError, ValueError, httpx.HTTPError):
                    if client: client.close()
                    client = None
                    time.sleep(.2)
            assert client is not None
            current = client.get("/api/bootstrap").json()
            assert len(current["plans"]) == len(plans)
            response = client.post(f"/api/plans/{plans[-1]['id']}/export")
            response.raise_for_status()
            print("PASS Windows: Unicode/spaces install & data paths, proxy-safe duplicate launch, browser workflow, backup/restore, restart, export")
        finally:
            if client:
                try: client.post("/api/shutdown")
                except httpx.HTTPError: pass
                client.close()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate(); process.wait(timeout=10)
