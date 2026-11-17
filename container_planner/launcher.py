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
import webbrowser
from pathlib import Path

import uvicorn
from platformdirs import user_data_path

from .api import create_app
from . import __version__
from .instance import StartupLock, coordinate


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
    startup = StartupLock(root)
    startup.acquire()
    try:
        reuse_url, freed_port = coordinate(instance, __version__)
        if reuse_url:
            if not args.no_browser:
                webbrowser.open(reuse_url)
            return
        run_server(root, instance, args, freed_port, startup)
    finally:
        startup.release()


def run_server(root, instance, args, freed_port, startup):
    front = resources()
    if not (front / "index.html").exists():
        raise RuntimeError("缺少界面文件。开发运行请先在frontend目录执行npm install和npm run build。")
    # Bind once and pass the same socket to Uvicorn, avoiding a free-port race.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port or freed_port or 0))
    port = sock.getsockname()[1]
    sock.listen(128)
    url = f"http://127.0.0.1:{port}"
    app = create_app(root, front)
    from .store import uid
    instance_id = uid()
    app.state.instance_id = instance_id
    app.add_event_handler("startup", startup.release)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None,
                                          proxy_headers=False, access_log=False))
    app.state.shutdown = lambda: setattr(server, "should_exit", True)
    instance.write_text(json.dumps({"url": url, "id": instance_id, "version": __version__}), encoding="utf-8")
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
