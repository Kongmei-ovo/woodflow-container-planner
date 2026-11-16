"""Native entry point: report even missing dependency/DLL startup failures."""
import multiprocessing
import os
import sys
import tempfile
import traceback
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def report_startup_error():
    root = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WoodFlow" / "ContainerPlanner"
            if sys.platform == "win32" else Path.home() / "Library/Application Support/ContainerPlanner")
    details = traceback.format_exc()
    try:
        root.mkdir(parents=True, exist_ok=True)
        path = root / "startup-error.txt"
        path.write_text(details, encoding="utf-8")
    except OSError:
        path = Path(tempfile.gettempdir()) / "WoodFlow-startup-error.txt"
        path.write_text(details, encoding="utf-8")
    message = f"木序未能启动。\n请先确认ZIP已完整解压，runtime和app文件夹保持完整。\n\n错误记录：{path}\n可运行‘遇到问题请运行自检.bat’并将报错反馈给提供者。"
    if sys.platform == "win32" and "--no-browser" not in sys.argv:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "木序启动提示", 0x10)
    if sys.stderr:
        print(message, details, file=sys.stderr)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        from container_planner.launcher import main
        main()
    except Exception:
        report_startup_error()
        sys.exit(1)
