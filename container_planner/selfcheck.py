"""User-run diagnostics, isolated from all business records."""
import argparse
import json
import multiprocessing
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from . import __version__
    default_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WoodFlow" / "ContainerPlanner"
    output = args.output or default_root / "自检结果.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"木序自检版本：{__version__}", f"系统：{platform.platform()}", f"架构：{platform.machine()}",
             f"Python：{platform.python_version()}", "自检使用虚构数据和临时目录，不读取真实订单。"]
    process = None
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = None
    code = 0
    try:
        from .api import create_app
        from .store import Store
        from .demo import load_demo
        from .service import snapshot_inputs
        from .jobs import run_job
        from .solver import validate
        from .exporting import export_plan
        from .excel import read_book
        lines.append("[通过] 程序依赖和本机排柜库可加载")
        with tempfile.TemporaryDirectory(prefix="木序 自检-") as tmp:
            temp = Path(tmp)
            store = Store(temp / "中文 资料目录")
            result = load_demo(store)
            project = store.get("project", result["project_id"])
            project["lines"][0]["batches"] = [{"date": "2027-01-11", "quantity": 350}, {"date": "2027-01-18", "quantity": 350}]
            snapshot = snapshot_inputs(project, store.list("product"))
            job = store.put("job", {"snapshot": snapshot, "project_id": project["id"], "name": "自检练习方案", "seconds": 2, "status": "queued"})
            worker = multiprocessing.get_context("spawn").Process(target=run_job, args=(str(store.root), job["id"]))
            worker.start(); worker.join(timeout=30)
            if worker.is_alive():
                worker.terminate(); worker.join(timeout=5)
                raise RuntimeError("排柜子进程超时")
            result = store.get("job", job["id"])
            assert result["status"] == "completed", result.get("message")
            plan = store.get("plan", result["plan_id"])
            assert len(plan["containers"]) == 4
            assert not validate(plan["containers"], snapshot["atoms"])
            lines.append("[通过] 中文路径、数据库、后台子进程、分工厂排柜与数量容量核对")
            xlsx = temp / "练习 排柜.xlsx"
            export_plan(plan, xlsx)
            assert {"排柜明细", "Summary"}.issubset(read_book(xlsx))
            lines.append("[通过] Excel写入和重新读取")
            root = Path(__file__).resolve().parent.parent
            server_data = temp / "浏览器 服务测试"
            process = subprocess.Popen([sys.executable, str(root / "run_planner.py"), "--data-dir", str(server_data), "--no-browser"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"本机服务提前退出：{process.returncode}")
                try:
                    url = json.loads((server_data / "instance.json").read_text())["url"]
                    with client.open(url + "/api/health", timeout=2) as res:
                        assert json.load(res)["ok"]
                    break
                except (OSError, ValueError):
                    time.sleep(.2)
            else:
                raise RuntimeError("本机服务未在20秒内启动")
            with client.open(url, timeout=3) as res:
                assert b'id="root"' in res.read()
            lines.append("[通过] 本机服务启动、界面文件和浏览器访问地址")
            client.open(urllib.request.Request(url + "/api/shutdown", data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=3).close()
            process.wait(timeout=15); process = None
        lines.append("结果：全部通过。可双击启动排柜工具；若界面仍无法打开，请附上本报告反馈。")
    except Exception:
        code = 1
        lines.append("[未通过] " + traceback.format_exc())
        lines.append("请将本报告和启动提示截图反馈给提供者。")
    finally:
        if process and process.poll() is None:
            process.terminate(); process.wait(timeout=10)
        output.write_text("\n".join(lines), encoding="utf-8-sig")
        print("\n".join(lines)); print(f"报告已保存：{output}")
    return code


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
