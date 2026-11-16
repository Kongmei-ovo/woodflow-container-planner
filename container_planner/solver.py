from __future__ import annotations

import copy
import math
import time
from collections import Counter, defaultdict
from decimal import Decimal

from ortools.sat.python import cp_model

from .service import FACTORY_ORDER
from .store import uid

LIMITS = {"20GP": {"cbm": "28", "weight": "22800"},
          "40GP": {"cbm": "58", "weight": "22800"},
          "40HQ": {"cbm": "68", "weight": "22800"}}
TYPES = list(LIMITS)
D = Decimal


def groupkey(atom):
    return atom["factory"], atom["warehouse"], atom["date"], atom.get("load_class", "REGULAR")


def groupsort(key):
    factory, warehouse, day, *rest = key
    return (FACTORY_ORDER.index(factory) if factory in FACTORY_ORDER else 100, factory, warehouse, day, *rest)


def totals(container, atoms):
    volume = weight = D(0)
    for allocation in container["allocations"]:
        atom = atoms[allocation["atom_id"]]
        volume += D(atom["cbm"]) * allocation["quantity"]
        weight += D(atom["weight"]) * allocation["quantity"]
    return volume, weight


def decorate(containers, atoms):
    index = {a["id"]: a for a in atoms}
    result = copy.deepcopy(containers)
    for c in result:
        volume, weight = totals(c, index)
        c["total_cbm"], c["total_weight"] = str(volume), str(weight)
    return result


def validate(containers, atoms, complete=True):
    index = {a["id"]: a for a in atoms}
    allocated = Counter()
    errors = []
    seen = set()
    for c in containers:
        if (not isinstance(c, dict) or not isinstance(c.get("allocations"), list)
                or not isinstance(c.get("id"), str) or not c["id"]):
            errors.append("柜结构无效：缺少柜标识或分配列表")
            continue
        if c.get("id") in seen:
            errors.append("柜编号重复")
        seen.add(c.get("id"))
        if not isinstance(c.get("type"), str) or c["type"] not in LIMITS:
            errors.append("未知柜型")
            continue
        if not c.get("allocations"):
            errors.append("空柜不能保存为正式方案")
        for row in c.get("allocations", []):
            if not isinstance(row, dict):
                errors.append("柜内分配格式无效")
                continue
            atom = index.get(row.get("atom_id")) if isinstance(row.get("atom_id"), str) else None
            q = row.get("quantity")
            if not atom or type(q) is not int or q <= 0:
                errors.append("柜内分配引用无效或数量不是正整数")
                continue
            if groupkey(atom) != (c.get("factory"), c.get("warehouse"), c.get("batch_date", c.get("date")), c.get("load_class", "REGULAR")):
                errors.append("柜内混有不同工厂、目的仓、发货批次或新品/常规品")
            if c.get("date"):
                try:
                    from datetime import date
                    date.fromisoformat(c["date"])
                except (ValueError, TypeError):
                    errors.append("柜的LSD须为有效日期")
            if atom["date"] and c.get("date") != atom["date"]:
                errors.append("已确认的订单交期不能直接改到其他日期")
            allocated[atom["id"]] += q
        if all(isinstance(row, dict) and isinstance(row.get("atom_id"), str) and row["atom_id"] in index and type(row.get("quantity")) is int
               for row in c.get("allocations", [])):
            v, w = totals(c, index)
            if v > D(LIMITS[c["type"]]["cbm"]):
                errors.append(f"{c.get('number', '')}柜超体积：{v}m³")
            if w > D(LIMITS[c["type"]]["weight"]):
                errors.append(f"{c.get('number', '')}柜超毛重：{w}kg")
    for atom in atoms:
        actual = allocated[atom["id"]]
        if actual > atom["quantity"] or (complete and actual != atom["quantity"]):
            errors.append(f"{atom['code']}数量不平：应排{atom['quantity']}，已排{actual}")
    return list(dict.fromkeys(errors))


def smallest_type(volume, weight):
    return next((t for t in TYPES if volume <= D(LIMITS[t]["cbm"]) and weight <= D(LIMITS[t]["weight"])), None)


def greedy(items):
    bins = []
    ordered = sorted(items, key=lambda p: (max(D(p["cbm"]) / 68, D(p["weight"]) / 22800), p["quantity"]), reverse=True)
    for p in ordered:
        q = p["quantity"]
        v, w = D(p["cbm"]), D(p["weight"])
        if not smallest_type(v, w):
            raise ValueError(f"{p['code']}单件已超过所有柜型的体积或重量上限，无法安排。")
        # Prefer an existing bin that can take the entire remainder, then the tightest fit.
        while q:
            options = []
            for i, b in enumerate(bins):
                capacity = min(int((D(68) - b["v"]) // v), int((D(22800) - b["w"]) // w))
                if capacity > 0:
                    options.append((capacity < q, abs(capacity - q), i, capacity))
            if options:
                _, _, i, capacity = min(options)
                b = bins[i]
            else:
                b = {"v": D(0), "w": D(0), "q": {}}
                bins.append(b)
                capacity = min(int(D(68) // v), int(D(22800) // w))
            take = min(q, capacity)
            b["q"][p["product_id"]] = b["q"].get(p["product_id"], 0) + take
            b["v"] += take * v
            b["w"] += take * w
            q -= take
    return [{"type": smallest_type(b["v"], b["w"]), "q": b["q"]} for b in bins]


def objective(bins, items):
    grades = {p["product_id"]: p.get("abc") or "未分级" for p in items}
    return (len(bins), sum(len(b["q"]) for b in bins),
            sum(len({grades[p] for p in b["q"]}) for b in bins),
            sum(int(LIMITS[b["type"]]["cbm"]) for b in bins))


def integer_coefficients(items, field, capacities):
    values = [D(i[field]) for i in items] + [D(c) for c in capacities]
    places = max(max(0, -v.as_tuple().exponent) for v in values)
    if places > 12:
        raise ValueError("计量精度超过12位小数，请审核产品资料。")
    scale = 10 ** places
    nums = [int(v * scale) for v in values]
    gcd = math.gcd(*nums)
    nums = [n // gcd for n in nums]
    if sum(n * i["quantity"] for n, i in zip(nums, items)) >= 2**60:
        raise ValueError("计量数值过大，请核实单位和数量。")
    return nums[:len(items)], nums[len(items):]


def optimize_group(items, budget):
    initial = greedy(items)
    best = initial
    n = len(initial)
    if n == 1:
        return initial, True
    vols, caps = integer_coefficients(items, "cbm", [LIMITS[t]["cbm"] for t in TYPES])
    weights, wcaps = integer_coefficients(items, "weight", [LIMITS[t]["weight"] for t in TYPES])
    model = cp_model.CpModel()
    use = [model.new_bool_var(f"use{b}") for b in range(n)]
    types = [[model.new_bool_var(f"type{b}_{t}") for t in range(3)] for b in range(n)]
    qty, present = {}, {}
    for i, p in enumerate(items):
        for b in range(n):
            qty[i, b] = model.new_int_var(0, p["quantity"], f"q{i}_{b}")
            present[i, b] = model.new_bool_var(f"p{i}_{b}")
            model.add(qty[i, b] <= p["quantity"] * present[i, b])
            model.add(qty[i, b] >= present[i, b])
            model.add(present[i, b] <= use[b])
        model.add(sum(qty[i, b] for b in range(n)) == p["quantity"])
    for b in range(n):
        model.add(sum(types[b]) == use[b])
        model.add(sum(qty[i, b] for i in range(len(items))) >= use[b])
        model.add(sum(vols[i] * qty[i, b] for i in range(len(items))) <= sum(caps[t] * types[b][t] for t in range(3)))
        model.add(sum(weights[i] * qty[i, b] for i in range(len(items))) <= sum(wcaps[t] * types[b][t] for t in range(3)))
        if b:
            model.add(use[b - 1] >= use[b])
    lower = max(math.ceil(sum(D(p["cbm"]) * p["quantity"] for p in items) / D(68)),
                math.ceil(sum(D(p["weight"]) * p["quantity"] for p in items) / D(22800)))
    model.add(sum(use) >= lower)
    for b, bin in enumerate(initial):
        model.add_hint(use[b], 1)
        for t, typ in enumerate(TYPES):
            model.add_hint(types[b][t], int(bin["type"] == typ))
        for i, p in enumerate(items):
            q = bin["q"].get(p["product_id"], 0)
            model.add_hint(qty[i, b], q)
            model.add_hint(present[i, b], int(q > 0))
    grade_presence = []
    for grade in sorted({p.get("abc") or "未分级" for p in items}):
        indices = [i for i, p in enumerate(items) if (p.get("abc") or "未分级") == grade]
        for b in range(n):
            var = model.new_bool_var(f"grade_{grade}_{b}")
            model.add_max_equality(var, [present[i, b] for i in indices])
            grade_presence.append(var)
    goals = [sum(use), sum(present.values()), sum(grade_presence),
             sum(int(LIMITS[TYPES[t]]["cbm"]) * types[b][t] for b in range(n) for t in range(3))]
    started = time.monotonic()
    proven = True
    for stage, goal in enumerate(goals):
        remaining = budget - (time.monotonic() - started)
        if remaining < .015:
            proven = False
            break
        if stage == 0 and lower == n:
            model.add(goal == n)
            continue
        model.minimize(goal)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(.01, remaining * (.5 if stage == 0 else .5 if stage == 1 else .65 if stage == 2 else 1))
        solver.parameters.num_search_workers = 4
        solver.parameters.random_seed = 42
        status = solver.solve(model)
        if status in (cp_model.MODEL_INVALID, cp_model.INFEASIBLE):
            raise ValueError("排柜模型校验失败：" + (model.validate() or solver.status_name(status)))
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            proven = False
            break
        candidate = []
        for b in range(n):
            if solver.value(use[b]):
                amounts = {p["product_id"]: solver.value(qty[i, b]) for i, p in enumerate(items) if solver.value(qty[i, b])}
                v = sum(D(p["cbm"]) * amounts.get(p["product_id"], 0) for p in items)
                w = sum(D(p["weight"]) * amounts.get(p["product_id"], 0) for p in items)
                candidate.append({"type": smallest_type(v, w), "q": amounts})
        if objective(candidate, items) <= objective(best, items):
            best = candidate
        proven = proven and status == cp_model.OPTIMAL
        model.add(goal == solver.value(goal))
        # Refresh every hint after an objective stage to avoid inconsistent old hints.
        model.clear_hints()
        for var in [*use, *(x for row in types for x in row), *qty.values(), *present.values(), *grade_presence]:
            model.add_hint(var, solver.value(var))
    return best, proven


def solve(snapshot, locked=None, seconds=30, progress=None):
    atoms = snapshot["atoms"]
    locked = copy.deepcopy(locked or [])
    errors = validate(locked, atoms, complete=False)
    if errors:
        raise ValueError("已锁定柜与当前订单不符：" + "；".join(errors))
    consumed = Counter()
    for c in locked:
        for row in c["allocations"]:
            consumed[row["atom_id"]] += row["quantity"]
    groups = defaultdict(list)
    for atom in atoms:
        q = atom["quantity"] - consumed[atom["id"]]
        if q:
            groups[groupkey(atom)].append({**atom, "quantity": q})
    containers = list(locked)
    proof = []
    started = time.monotonic()
    keys = sorted(groups, key=groupsort)
    for gi, key in enumerate(keys):
        entries = groups[key]
        merged = {}
        for a in entries:
            if a["product_id"] not in merged:
                merged[a["product_id"]] = {**a, "quantity": 0}
            merged[a["product_id"]]["quantity"] += a["quantity"]
            if merged[a["product_id"]].get("abc") != a.get("abc"):
                merged[a["product_id"]]["abc"] = "多等级"
        budget = max(.01, (seconds - (time.monotonic() - started)) / max(1, len(keys) - gi))
        bins, proven = optimize_group(list(merged.values()), budget)
        if locked:
            # Locked distributions can affect SKU splitting; never claim global optimality.
            proven = False
        proof.append({"factory": key[0], "warehouse": key[1], "date": key[2], "optimal": proven})
        pending = {p: [[a["id"], a["quantity"]] for a in entries if a["product_id"] == p] for p in merged}
        for bin in bins:
            allocations = []
            for product_id, q in bin["q"].items():
                for rest in pending[product_id]:
                    take = min(q, rest[1])
                    if take:
                        allocations.append({"atom_id": rest[0], "quantity": take})
                        rest[1] -= take
                        q -= take
                    if not q:
                        break
            containers.append({"id": uid(), "factory": key[0], "warehouse": key[1], "date": key[2], "batch_date": key[2], "load_class": key[3],
                               "type": bin["type"], "locked": False, "allocations": allocations})
        if progress:
            progress(gi + 1, len(keys), " / ".join(key))
    containers.sort(key=lambda c: groupsort((c["factory"], c["warehouse"], c.get("batch_date", c["date"]), c.get("load_class", "REGULAR"))))
    for i, c in enumerate(containers, 1):
        c["number"] = i
    errors = validate(containers, atoms)
    if errors:
        raise ValueError("方案校验未通过：" + "；".join(errors))
    return {"containers": decorate(containers, atoms), "proof": proof,
            "optimal": bool(proof) and all(p["optimal"] for p in proof),
            "seconds": round(time.monotonic() - started, 2)}
