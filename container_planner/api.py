from __future__ import annotations

import copy
import asyncio
import io
import json
import multiprocessing
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from platformdirs import user_data_path

from .excel import integer, number, read_book, suggest, text
from .exporting import export_plan
from .jobs import run_job
from .service import candidates, commit_import, product_issues, project_view, snapshot_inputs
from .solver import LIMITS, decorate, validate
from .store import Conflict, Store, uid
from . import __version__


def create_app(root: Path | None = None, frontend: Path | None = None):
    store = Store(root or Path(os.environ.get("PLANNER_DATA_DIR", user_data_path("ContainerPlanner", "WoodFlow"))))
    app = FastAPI(title="智能排柜工作台", version=__version__)
    app.state.store = store
    app.state.processes = {}
    app.state.operation_lock = threading.RLock()
    request_lock = asyncio.Lock()

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Browser sites cannot submit changes to the local service via cross-origin requests.
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"localhost", "127.0.0.1", "testserver"}:
            return JSONResponse({"detail": "仅允许本机访问"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {f"http://{request.headers.get('host')}", "http://localhost:5173", "http://127.0.0.1:5173"}:
            return JSONResponse({"detail": "不接受其他网站的请求"}, status_code=403)
        # Serialize local business requests, so restoring files cannot race an edit.
        async with request_lock:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def value_error(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409 if isinstance(exc, Conflict) else 422)

    @app.exception_handler(KeyError)
    async def missing(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    def list_projects():
        products = {p["id"]: p for p in store.list("product")}
        from .service import line_issues
        return [{k: v for k, v in p.items() if k != "lines"} | {
            "line_count": len(p["lines"]), "quantity": sum(l.get("updated_qty") or 0 for l in p["lines"]),
            "issue_count": sum(bool(line_issues(l, products, p.get("allow_undated", False), p.get("quantity_rules", False))) for l in p["lines"])} for p in store.list("project")]

    @app.get("/api/bootstrap")
    def bootstrap():
        products = store.list("product")
        plans = [{k: v for k, v in p.items() if k not in ("snapshot", "containers")} |
                 {"container_count": len(p["containers"])} for p in store.list("plan")]
        return {"products": [{**p, "issues": product_issues(p)} for p in products], "projects": list_projects(),
                "plans": plans, "imports": [{k: v for k, v in imp.items() if k not in ("diagnostics", "sheets")}
                                              for imp in store.list("import")],
                "jobs": [{k: v for k, v in j.items() if k not in ("snapshot", "locked")} for j in store.list("job")[-10:]],
                "mappings": store.list("mapping"), "limits": LIMITS, "data_dir": str(store.root), "version": __version__}

    @app.post("/api/demo")
    def demo():
        from .demo import load_demo
        with app.state.operation_lock:
            return load_demo(store)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "instance_id": getattr(app.state, "instance_id", None)}

    @app.post("/api/shutdown")
    def shutdown():
        if any(p.is_alive() for p in app.state.processes.values()):
            raise ValueError("正在排柜，请完成后再退出。")
        callback = getattr(app.state, "shutdown", None)
        if callback:
            threading.Timer(.3, callback).start()
        return {"ok": True}

    @app.post("/api/products")
    def create_product(payload: dict = Body(...)):
        if not text(payload.get("description")):
            raise ValueError("请填写产品名称。")
        p = {"code": text(payload.get("code")), "oem": text(payload.get("oem")),
             "barcode": text(payload.get("barcode")), "description": text(payload["description"]),
             "factory": text(payload.get("factory")), "factory_candidates": [],
             "cbm": number(payload.get("cbm")), "weight": number(payload.get("weight")), "conflicts": [], "sources": []}
        return store.put("product", p, action="人工新增产品")

    @app.post("/api/products/assign-factory")
    def assign_factory(payload: dict = Body(...)):
        factory = text(payload.get("factory"))
        if not factory or not payload.get("products"):
            raise ValueError("请选择产品和工厂。")
        items = []
        for row in payload["products"]:
            p = store.get("product", row["id"])
            p.update(factory=factory, factory_candidates=[factory])
            items.append(("product", p, p["id"], row["revision"], "批量确认工厂归属"))
        store.put_many(items)
        return {"count": len(items)}

    @app.patch("/api/products/{product_id}")
    def edit_product(product_id: str, payload: dict = Body(...)):
        p = store.get("product", product_id)
        expected = payload.get("revision")
        if expected is None:
            raise ValueError("缺少记录版本，请刷新。")
        for field in ("code", "oem", "barcode", "description", "factory"):
            if field in payload:
                p[field] = text(payload[field])
        for field in ("cbm", "weight"):
            if field in payload:
                p[field] = number(payload[field])
        if not p["description"]:
            raise ValueError("请填写产品名称。")
        if payload.get("confirm_conflicts"):
            p["conflicts"] = []
            if p.get("factory"):
                p["factory_candidates"] = [p["factory"]]
        return store.put("product", p, product_id, expected, "人工修正产品资料")

    @app.get("/api/candidates")
    def get_candidates(q: str = ""):
        return candidates(q, store.list("product"))

    @app.post("/api/imports/preview")
    async def preview(file: UploadFile = File(...)):
        filename = Path((file.filename or "工作簿.xlsx").replace("\\", "/")).name
        ext = Path(filename).suffix.lower()
        if ext not in {".xlsx", ".csv"}:
            raise ValueError("支持 .xlsx、.csv；.xls 请另存为 .xlsx。")
        import_id = uid()
        stored = import_id + ext
        path = store.root / "originals" / stored
        size = 0
        try:
            with path.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 60_000_000:
                        raise ValueError("单个文件不能超过60MB。")
                    stream.write(chunk)
            book = read_book(path)
            sheets = {name: suggest(rows) for name, rows in book.items()}
            if not sheets:
                raise ValueError("文件内没有可读取的工作表。")
            return store.put("import", {"filename": filename, "stored_name": stored, "status": "staged",
                                         "sheets": sheets, "size": size}, import_id, action="保留导入原文件")
        except Exception as exc:
            path.unlink(missing_ok=True)
            if isinstance(exc, (ValueError, HTTPException)):
                raise
            raise ValueError(f"无法读取工作簿：{exc}") from exc

    @app.get("/api/imports/{import_id}")
    def import_detail(import_id: str):
        return store.get("import", import_id)

    @app.get("/api/imports/{import_id}/sheet")
    def import_sheet(import_id: str, sheet: str, header_row: int = 1):
        imp = store.get("import", import_id)
        book = read_book(store.root / "originals" / imp["stored_name"])
        if sheet not in book:
            raise ValueError("工作表不存在。")
        rows = book[sheet]
        result = suggest(rows, header_row=header_row)
        result["preview"] = [r for r in rows if r["row"] >= header_row][:8]
        return result

    @app.get("/api/imports/{import_id}/original")
    def original(import_id: str):
        imp = store.get("import", import_id)
        return FileResponse(store.root / "originals" / imp["stored_name"], filename=imp["filename"])

    @app.post("/api/imports/{import_id}/commit")
    def do_import(import_id: str, config: dict = Body(...)):
        with app.state.operation_lock:
            return commit_import(store, store.get("import", import_id), config)

    @app.get("/api/projects/{project_id}")
    def project_detail(project_id: str):
        return project_view(store, store.get("project", project_id))

    @app.patch("/api/projects/{project_id}/lines/{line_id}")
    def edit_line(project_id: str, line_id: str, payload: dict = Body(...)):
        p = store.get("project", project_id)
        if payload.get("revision") is None:
            raise ValueError("缺少订单版本，请刷新。")
        line = next((l for l in p["lines"] if l["id"] == line_id), None)
        if line is None:
            raise KeyError("订单行不存在")
        for field in ("product_id", "warehouse", "abc", "exclusion_reason"):
            if field in payload:
                line[field] = text(payload[field])
        if payload.get("product_id"):
            store.get("product", payload["product_id"])
        if "updated_qty" in payload:
            previous_qty = line.get("updated_qty")
            line["updated_qty"] = integer(payload["updated_qty"])
            if line["updated_qty"] is None or line["updated_qty"] < 0:
                raise ValueError("数量必须是非负整数。")
            if line["updated_qty"] != previous_qty:
                line["quantity_note"] = "人工调整；较原量变化" + str(line["updated_qty"] - (line.get("original_qty") or 0)) + "件"
        if line.get("original_qty") is None and "original_qty" in payload:
            line["original_qty"] = integer(payload["original_qty"])
            if line["original_qty"] is None or line["original_qty"] < 0:
                raise ValueError("补录的原始数量必须是非负整数。")
        if "batches" in payload:
            if not isinstance(payload["batches"], list):
                raise ValueError("批次格式无效。")
            line["batches"] = [{"date": text(b.get("date")), "quantity": integer(b.get("quantity"))}
                               for b in payload["batches"] if isinstance(b, dict)]
        if "excluded" in payload:
            line["excluded"] = bool(payload["excluded"])
        if payload.get("bind_matching") and line.get("product_id"):
            from .excel import normalized, codekey
            for other in p["lines"]:
                if (codekey(other["source_code"]) == codekey(line["source_code"])
                        and normalized(other["description"]) == normalized(line["description"])):
                    other["product_id"] = line["product_id"]
        result = store.put("project", p, project_id, payload["revision"], "人工审核订单行")
        return project_view(store, result)

    @app.post("/api/projects/{project_id}/rules")
    def apply_project_rules(project_id: str, payload: dict = Body(...)):
        from .quantities import adjust_quantities
        p = store.get("project", project_id)
        if "allow_undated" in payload:
            if type(payload["allow_undated"]) is not bool:
                raise ValueError("请选择是否允许先排柜后填写LSD。")
            p["allow_undated"] = payload["allow_undated"]
        if payload.get("auto_adjust"):
            adjust_quantities(p)
        saved = store.put("project", p, project_id, payload.get("revision", -1), "应用凑整补量或待填LSD规则")
        return project_view(store, saved)

    @app.post("/api/projects/{project_id}/assign-batch")
    def assign_batch(project_id: str, payload: dict = Body(...)):
        from datetime import date
        p = store.get("project", project_id)
        day = date.fromisoformat(text(payload.get("date"))).isoformat()
        selected = set(payload.get("line_ids", []))
        if not selected or not selected.issubset({l["id"] for l in p["lines"]}):
            raise ValueError("请选择有效的订单行。")
        for line in p["lines"]:
            if line["id"] in selected:
                q = line.get("updated_qty")
                if type(q) is not int or q < 0 or line.get("excluded"):
                    raise ValueError("选中的行含无效数量或已排除订单，请先审核。")
                line["batches"] = [{"date": day, "quantity": q}] if q else []
        saved = store.put("project", p, project_id, payload.get("revision", -1), "人工批量指定发货批次")
        return project_view(store, saved)

    @app.post("/api/projects/{project_id}/exclude-lines")
    def exclude_lines(project_id: str, payload: dict = Body(...)):
        p = store.get("project", project_id)
        ids = set(payload.get("line_ids", []))
        reason = text(payload.get("reason"))
        if not reason or not ids or not ids.issubset({l["id"] for l in p["lines"]}):
            raise ValueError("请选择订单行并填写本次不参与排柜的原因。")
        for line in p["lines"]:
            if line["id"] in ids:
                line.update(excluded=True, exclusion_reason=reason)
        saved = store.put("project", p, project_id, payload.get("revision", -1), "人工批量排除本次订单")
        return project_view(store, saved)

    @app.post("/api/projects/{project_id}/solve")
    def start_solve(project_id: str, payload: dict = Body(default={})):
        with app.state.operation_lock:
            processes = app.state.processes
            if any(process.is_alive() for process in processes.values()):
                raise ValueError("已有任务正在计算，请等待当前任务完成。")
            project = store.get("project", project_id)
            if payload.get("revision") != project["revision"]:
                raise Conflict("订单已更新，请刷新审核结果后再排柜。")
            snapshot = snapshot_inputs(project, store.list("product"))
            seconds = payload.get("seconds", 30)
            if type(seconds) not in (int, float) or not 1 <= seconds <= 300:
                raise ValueError("计算时间应在1至300秒之间。")
            locked = []
            if payload.get("base_plan_id"):
                base = store.get("plan", payload["base_plan_id"])
                if base["project_id"] != project_id:
                    raise ValueError("基础方案属于其他订单。")
                locked = [c for c in base["containers"] if c.get("locked")]
            errors = validate(locked, snapshot["atoms"], complete=False)
            if errors:
                raise ValueError("已锁定柜与当前订单不符，请先解除锁定：" + "；".join(errors))
            job = store.put("job", {"project_id": project_id, "snapshot": snapshot,
                                    "name": text(payload.get("name")) or project["name"], "seconds": seconds,
                                    "base_plan_id": payload.get("base_plan_id"), "locked": locked,
                                    "status": "queued", "done": 0, "total": 0, "message": "等待计算"}, action="提交排柜任务")
            process = multiprocessing.get_context("spawn").Process(target=run_job, args=(str(store.root), job["id"]))
            process.start()
            processes[job["id"]] = process
            return {"id": job["id"], "status": "queued"}

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str):
        job = store.get("job", job_id)
        process = app.state.processes.get(job_id)
        if process is not None and job["status"] in {"completed", "failed"}:
            process.join(timeout=.5)
        if job["status"] in {"queued", "running"} and (process is None or (not process.is_alive() and process.exitcode is not None)):
            job = store.put("job", {**job, "status": "failed", "message": "计算进程中断，请重新排柜。"}, job_id)
        return {k: v for k, v in job.items() if k not in ("snapshot", "locked")}

    @app.get("/api/plans/{plan_id}")
    def plan_detail(plan_id: str):
        return store.get("plan", plan_id)

    @app.post("/api/plans/{plan_id}/versions")
    def plan_version(plan_id: str, payload: dict = Body(...)):
        old = store.get("plan", plan_id)
        containers = payload.get("containers")
        if not isinstance(containers, list) or len(containers) > 1000:
            raise ValueError("请提交有效的柜列表。")
        errors = validate(containers, old["snapshot"]["atoms"])
        if errors:
            raise ValueError("；".join(errors))
        for i, c in enumerate(containers, 1):
            c["number"] = i
        return store.put("plan", {"name": text(payload.get("name")) or old["name"], "project_id": old["project_id"],
                                  "parent_id": plan_id, "snapshot": old["snapshot"], "optimal": False, "proof": [],
                                  "containers": decorate(containers, old["snapshot"]["atoms"]), "seconds": 0}, action="人工调整并另存方案")

    @app.post("/api/plans/{plan_id}/export")
    def export(plan_id: str):
        with app.state.operation_lock:
            plan = store.get("plan", plan_id)
            export_id = uid()
            path = store.root / "exports" / f"{export_id}.xlsx"
            try:
                export_plan(plan, path)
                record = store.put("export", {"plan_id": plan_id, "filename": f"排柜方案-{plan['name'][:80]}.xlsx",
                                               "stored_name": path.name}, export_id, action="导出已校验Excel")
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return record

    @app.get("/api/exports")
    def exports():
        return store.list("export")

    @app.get("/api/exports/{export_id}")
    def download(export_id: str):
        e = store.get("export", export_id)
        return FileResponse(store.root / "exports" / e["stored_name"], filename=e["filename"],
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.get("/api/history")
    def history(kind: str | None = None, id: str | None = None):
        return store.history(kind, id)

    @app.get("/api/backup")
    def backup():
        with app.state.operation_lock, tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "planner.sqlite3"
            with store.connection() as db, closing(sqlite3.connect(target)) as dest:
                db.backup(dest)
            stream = io.BytesIO()
            with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
                archive.write(target, "planner.sqlite3")
                archive.writestr("manifest.json", json.dumps({"version": 1}))
                for folder in ("originals", "exports"):
                    for path in (store.root / folder).iterdir():
                        if path.is_file():
                            archive.write(path, f"{folder}/{path.name}")
            return Response(stream.getvalue(), media_type="application/zip",
                            headers={"Content-Disposition": 'attachment; filename="container-planner-backup.zip"'})

    @app.post("/api/restore")
    async def restore(file: UploadFile = File(...)):
        raw = await file.read(250_000_001)
        if len(raw) > 250_000_000:
            raise ValueError("备份超过250MB，请使用数据目录迁移。")
        with app.state.operation_lock:
            if any(p.is_alive() for p in app.state.processes.values()):
                raise ValueError("排柜计算中，请等待完成后恢复。")
            with tempfile.TemporaryDirectory(dir=store.root.parent) as tmp:
                temp = Path(tmp)
                try:
                    with ZipFile(io.BytesIO(raw)) as archive:
                        if sum(e.file_size for e in archive.infolist()) > 500_000_000:
                            raise ValueError("备份解压后过大。")
                        for name in archive.namelist():
                            parts = Path(name).parts
                            if name not in {"manifest.json", "planner.sqlite3"} and not (
                                    len(parts) == 2 and parts[0] in {"originals", "exports"} and parts[1] not in {".", ".."}):
                                raise ValueError("备份包含无效路径。")
                            if "\\" in name or Path(name).is_absolute():
                                raise ValueError("备份包含无效路径。")
                        archive.extractall(temp)
                    if json.loads((temp / "manifest.json").read_text())["version"] != 1:
                        raise ValueError("备份版本不兼容。")
                    dbfile = temp / "planner.sqlite3"
                    with closing(sqlite3.connect(dbfile.as_uri() + "?mode=ro", uri=True)) as db:
                        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise ValueError("备份数据库损坏。")
                        db.execute("SELECT kind,id,data,revision FROM records LIMIT 1").fetchall()
                        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                            raise ValueError("备份数据库版本不兼容。")
                        for kind, raw_record in db.execute("SELECT kind,data FROM records WHERE kind IN ('import','export')"):
                            record = json.loads(raw_record)
                            filename = record.get("stored_name", "")
                            folder = "originals" if kind == "import" else "exports"
                            if not filename or Path(filename).name != filename or "\\" in filename or not (temp / folder / filename).is_file():
                                raise ValueError("备份缺少所引用的原文件或导出文件。")
                    # Close/checkpoint all SQLite handles before moving on Windows.
                    with store.connection() as db:
                        db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
                    for suffix in ("-wal", "-shm"):
                        Path(str(store.path) + suffix).unlink(missing_ok=True)
                    # Swap complete data components on the same filesystem; rollback
                    # any partial swap. Logs and the live instance file stay in place.
                    previous = store.root.with_name(store.root.name + ".before-restore-" + uid()[:8])
                    for folder in ("originals", "exports"):
                        (temp / folder).mkdir(exist_ok=True)
                    previous.mkdir()
                    names = ["planner.sqlite3", "originals", "exports"]
                    old_moved, new_moved = [], []
                    try:
                        for name in names:
                            os.replace(store.root / name, previous / name)
                            old_moved.append(name)
                        for name in names:
                            os.replace(temp / name, store.root / name)
                            new_moved.append(name)
                    except Exception:
                        for name in reversed(new_moved):
                            os.replace(store.root / name, temp / name)
                        for name in reversed(old_moved):
                            os.replace(previous / name, store.root / name)
                        raise
                    return {"ok": True, "previous_data": str(previous)}
                except (ValueError, KeyError):
                    raise
                except Exception as exc:
                    raise ValueError(f"无法恢复该备份：{exc}") from exc

    if frontend and frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
