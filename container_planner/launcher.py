from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn
from platformdirs import user_data_path

from .api import create_app


def resources():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "frontend"
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="木序 · 本地智能排柜工作台")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    root = args.data_dir or Path(os.environ.get("PLANNER_DATA_DIR", user_data_path("ContainerPlanner", "WoodFlow")))
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    log = root / "application.log"
    logging.basicConfig(filename=log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not sys.stdout:
        sys.stdout = log.open("a", encoding="utf-8")
    if not sys.stderr:
        sys.stderr = log.open("a", encoding="utf-8")
    instance = root / "instance.json"
    try:
        old = json.loads(instance.read_text())
        local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with local_http.open(old["url"] + "/api/health", timeout=1) as response:
            health = json.load(response)
        if health.get("instance_id") == old.get("id") and health.get("instance_id"):
            if not args.no_browser:
                webbrowser.open(old["url"])
            return
    except (OSError, ValueError, KeyError):
        pass
    front = resources()
    if not (front / "index.html").exists():
        raise RuntimeError("缺少界面文件。开发运行请先在frontend目录执行npm install和npm run build。")
    # Bind once and pass the same socket to Uvicorn, avoiding a free-port race.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    sock.listen(128)
    url = f"http://127.0.0.1:{port}"
    app = create_app(root, front)
    from .store import uid
    instance_id = uid()
    app.state.instance_id = instance_id
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None,
                                          proxy_headers=False, access_log=False))
    app.state.shutdown = lambda: setattr(server, "should_exit", True)
    instance.write_text(json.dumps({"url": url, "id": instance_id}), encoding="utf-8")
    logging.info("工作台地址：%s", url)

    def show():
        for _ in range(100):
            if server.started:
                try:
                    opened = webbrowser.open(url)
                except Exception:
                    logging.exception("无法打开默认浏览器")
                    opened = False
                if not opened and sys.platform == "win32":
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, f"工具已启动。请在浏览器中打开：\n{url}", "木序工作台地址", 0)
                return
            time.sleep(.1)
    if not args.no_browser:
        threading.Thread(target=show, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
        try:
            if json.loads(instance.read_text()).get("id") == instance_id:
                instance.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
