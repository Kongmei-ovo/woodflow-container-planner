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
    sys.path.insert(0, str(root))
    from container_planner import __version__
    binary = root / "dist" / ("WoodFlow.app/Contents/MacOS/WoodFlow" if sys.platform == "darwin" else "WoodFlow/WoodFlow.exe")
    command = [str(binary)]
    if args.package_root and sys.platform == "darwin":
        command = [str(args.package_root / "WoodFlow.app/Contents/MacOS/WoodFlow")]
    if args.windows_portable:
        portable = args.package_root or root / "dist/WoodFlow-Windows-x64"
        command = [str(portable / "runtime/pythonw.exe"), str(portable / "app/run_planner.py")]
    with tempfile.TemporaryDirectory(prefix="木序 启动测试-") as temp:
        directory = Path(temp)
        # Start a legacy protocol instance with synthetic records, then double-click
        # the native package without first quitting the old app.
        from container_planner.demo import load_demo
        from container_planner.store import Store
        marker = load_demo(Store(directory))['project_id']
        legacy = subprocess.Popen([sys.executable, str(root / 'scripts/legacy_launch_fixture.py'), '--data-dir', str(directory), '--no-browser'], cwd=root)
        old_url = None
        try:
            for _ in range(150):
                if legacy.poll() is not None:
                    raise RuntimeError('Legacy upgrade fixture exited early')
                try:
                    instance = json.loads((directory / 'instance.json').read_text())
                    with httpx.Client(base_url=instance['url'], trust_env=False) as old_client:
                        if old_client.get('/api/health').json()['version'] == '1.0.0':
                            old_url = instance['url']; break
                except (OSError, ValueError, httpx.HTTPError):
                    time.sleep(.2)
            if not old_url:
                raise RuntimeError('Legacy upgrade fixture did not start')
            process = subprocess.Popen([*command, "--data-dir", str(directory), "--no-browser"], cwd=root)
        except BaseException:
            legacy.terminate(); legacy.wait(timeout=15)
            raise
        client = None
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError(f"打包程序提前退出：{process.returncode}")
                try:
                    instance = json.loads((directory / "instance.json").read_text())
                    client = httpx.Client(base_url=instance["url"], timeout=30, trust_env=False)
                    if client.get("/api/health").json().get("version") == __version__:
                        break
                except (OSError, ValueError, httpx.HTTPError):
                    if client:
                        client.close()
                    client = None
                    time.sleep(.2)
            if not client:
                raise RuntimeError("打包程序未能启动")
            legacy.wait(timeout=15)
            assert client.base_url == httpx.URL(old_url), 'Upgrade should reuse the old local URL'
            assert client.get('/api/projects/' + marker).status_code == 200, 'Upgrade must preserve orders'
            duplicate = subprocess.run([*command, '--data-dir', str(directory), '--no-browser'], cwd=root, timeout=15)
            assert duplicate.returncode == 0, 'Same-version duplicate launch must reuse the running app'
            older = subprocess.run([sys.executable, str(root / 'scripts/legacy_launch_fixture.py'), '--data-dir', str(directory), '--no-browser'], cwd=root, timeout=15)
            assert older.returncode == 0 and process.poll() is None, 'Older app must reuse newer service'
            assert client.get("/api/health").json()["version"] == __version__, "打包版本与源码不一致"
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
            print("PASS: automatic upgrade takeover → data preserved → duplicate and older launches reuse newer service → packaged runtime → CSV imports → factory isolation → spawned solver → Excel download → clean exit")
        except Exception:
            log = directory / "application.log"
            if log.exists():
                print(log.read_text(errors="replace")[-6000:])
            raise
        finally:
            if client:
                client.close()
            if legacy.poll() is None:
                legacy.terminate(); legacy.wait(timeout=15)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
