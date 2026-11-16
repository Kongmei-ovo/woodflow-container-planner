from __future__ import annotations

from pathlib import Path

from .solver import solve
from .store import Store


def run_job(root: str, job_id: str):
    store = Store(Path(root))
    job = store.get("job", job_id)
    try:
        job = store.put("job", {**job, "status": "running", "message": "正在建立排柜模型"}, job_id)

        def progress(done, total, group):
            nonlocal job
            job = store.put("job", {**job, "done": done, "total": total, "message": group}, job_id)

        result = solve(job["snapshot"], job.get("locked"), job["seconds"], progress)
        plan = store.put("plan", {"name": job["name"], "project_id": job["project_id"],
                                  "parent_id": job.get("base_plan_id"), "snapshot": job["snapshot"], **result},
                         action="生成排柜方案")
        store.put("job", {**job, "status": "completed", "plan_id": plan["id"], "message": "排柜完成"}, job_id)
    except Exception as exc:
        store.put("job", {**job, "status": "failed", "message": str(exc)}, job_id)
