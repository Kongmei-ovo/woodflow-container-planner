"""Exercise the packaged native runtime, including spawned solver and Excel export."""
import json
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows-portable", action="store_true")
    parser.add_argument("--package-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    binary = root / "dist" / ("WoodFlow.app/Contents/MacOS/WoodFlow" if sys.platform == "darwin" else "WoodFlow/WoodFlow.exe")
    command = [str(binary)]
    if args.windows_portable:
        portable = args.package_root or root / "dist/WoodFlow-Windows-x64"
        command = [str(portable / "runtime/pythonw.exe"), str(portable / "app/run_planner.py")]
    with tempfile.TemporaryDirectory(prefix="木序 启动测试-") as temp:
        directory = Path(temp)
        process = subprocess.Popen([*command, "--data-dir", str(directory), "--no-browser"], cwd=root)
        client = None
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError(f"打包程序提前退出：{process.returncode}")
                try:
                    instance = json.loads((directory / "instance.json").read_text())
                    client = httpx.Client(base_url=instance["url"], timeout=30, trust_env=False)
                    if client.get("/api/health").json()["ok"]:
                        break
                except (OSError, ValueError, httpx.HTTPError):
                    if client:
                        client.close()
                    client = None
                    time.sleep(.2)
            if not client:
                raise RuntimeError("打包程序未能启动")
            assert "root" in client.get("/").text

            def call(method, path, **kwargs):
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()

            def upload(data, kind):
                imp = call("POST", "/api/imports/preview", files={"file": ("smoke.csv", data.encode("utf-8"))})
                return call("POST", f"/api/imports/{imp['id']}/commit", json={"kind": kind, "sheet": "CSV",
                            "header_row": 1, "mapping": imp["sheets"]["CSV"]["mapping"], "year": 2026})

            upload("PRODUCT CODE,OEM CODE,Product Description,CBM,G.W\nA,OEM-A,SMOKE TEST,.1,10\n", "catalog")
            upload("Product code,Product Description,Factory\nA,SMOKE TEST,利泰\n", "factory")
            order = upload("Item ID,Item Name,DCSYD,LSD\nA,SMOKE TEST,700,2026/12/21\n", "order")
            p = call("GET", f"/api/projects/{order['project_id']}")
            job = call("POST", f"/api/projects/{p['id']}/solve", json={"revision": p["revision"], "seconds": 2})
            for _ in range(150):
                job = call("GET", f"/api/jobs/{job['id']}")
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(.2)
            assert job["status"] == "completed", job
            plan = call("GET", f"/api/plans/{job['plan_id']}")
            assert len(plan["containers"]) == 2
            exported = call("POST", f"/api/plans/{plan['id']}/export")
            assert client.get(f"/api/exports/{exported['id']}").content.startswith(b"PK")
            # Completed results may arrive just before the child process exits.
            for _ in range(50):
                response = client.post("/api/shutdown")
                if response.status_code != 422:
                    response.raise_for_status()
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("后台计算进程未能正常结束")
            process.wait(timeout=15)
            print("PASS: packaged runtime → CSV imports → factory isolation → spawned solver → Excel download → clean exit")
        except Exception:
            log = directory / "application.log"
            if log.exists():
                print(log.read_text(errors="replace")[-6000:])
            raise
        finally:
            if client:
                client.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
