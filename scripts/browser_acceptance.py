"""Launch the source app with an isolated empty directory for browser acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    subprocess.run([sys.executable, "scripts/browser_fixtures.py"], cwd=ROOT, check=True)
    with tempfile.TemporaryDirectory(prefix="woodflow-browser-") as directory:
        process = subprocess.Popen([sys.executable, str(ROOT / "run_planner.py"), "--data-dir", directory, "--no-browser"], cwd=ROOT)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = None
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError("浏览器测试服务提前退出")
                try:
                    url = json.loads((Path(directory)/"instance.json").read_text())["url"]
                    opener.open(url+"/api/health", timeout=2).close()
                    break
                except (OSError, ValueError):
                    time.sleep(.2)
            else:
                raise RuntimeError("浏览器测试服务启动超时")
            subprocess.run(["node", "scripts/e2e.cjs"], cwd=ROOT, env={**os.environ, "PLANNER_TEST_URL":url}, check=True)
        finally:
            if url:
                try:
                    opener.open(urllib.request.Request(url+"/api/shutdown", data=b"{}", headers={"Content-Type":"application/json"}), timeout=3).close()
                except OSError:
                    pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate(); process.wait(timeout=10)
