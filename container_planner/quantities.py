"""Explicit, idempotent quantity suggestions against immutable source quantities."""
from collections import defaultdict
from decimal import Decimal
from .excel import codekey, normalized


def grouped_lines(project):
    groups = defaultdict(list)
    for line in project["lines"]:
        if not line.get("excluded"):
            key = line.get("product_id") or (codekey(line.get("source_code")), normalized(line.get("description")))
            groups[key].append(line)
    return groups


def refresh_quantity_info(project):
    if not project.get("quantity_rules"):
        return project
    warnings = []
    for lines in grouped_lines(project).values():
        name = lines[0].get("source_code") or lines[0]["description"]
        if any(type(l.get("original_qty")) is not int or type(l.get("updated_qty")) is not int for l in lines):
            warnings.append(f"{name}：数量尚未确认，无法核对四仓合计。")
            continue
        original = sum(l["original_qty"] for l in lines)
        total = sum(l["updated_qty"] for l in lines)
        for line in lines:
            line["quantity_group_original"], line["quantity_group_updated"] = original, total
        if 0 < total < 100:
            warnings.append(f"{name}：四仓合计原订{original}件，目前{total}件，仍不足100件；自动补量最多+30件。")
        if total > original + 30:
            warnings.append(f"{name}：人工调整后总增量{total-original}件，超过自动补量上限30件，请核实。")
        rounded = sum(((l["updated_qty"]+4)//5)*5 for l in lines)
        if rounded > original+30 and any(l["updated_qty"] % 5 for l in lines):
            warnings.append(f"{name}：凑整将超过+30件，需人工处理。")
    project["quantity_warnings"] = warnings
    return project


def adjust_quantities(project):
    groups = grouped_lines(project)
    warnings = []
    for lines in groups.values():
        name = lines[0].get("source_code") or lines[0]["description"]
        if any(type(l.get("original_qty")) is not int or type(l.get("updated_qty")) is not int for l in lines):
            warnings.append(f"{name}：数量尚未确认，暂不自动调整。")
            continue
        original = sum(l["original_qty"] for l in lines)
        active = [l for l in lines if l["original_qty"] > 0 and l["updated_qty"] > 0]
        proposed = {l["id"]: ((l["updated_qty"] + 4) // 5) * 5 for l in active}
        cap = original + 30
        total = sum(proposed.values()) + sum(l["updated_qty"] for l in lines if l not in active)
        if total > cap:
            warnings.append(f"{name}：凑整后将超过原订总量+30件，未自动调整，请人工核实。")
            continue
        target = max(total, min(100, (cap // 5) * 5)) if active else 0
        # Allocate 5-piece blocks by the greatest deficit to the original port ratio.
        weight = sum(l["original_qty"] for l in active)
        while total < target and active:
            chosen = max(active, key=lambda l: (Decimal(target) * l["original_qty"] / weight - proposed[l["id"]], l["original_qty"], l["id"]))
            proposed[chosen["id"]] += 5
            total += 5
        for line in active:
            previous = line["updated_qty"]
            updated = proposed[line["id"]]
            line["updated_qty"] = updated
            if updated != previous:
                batches = line.get("batches", [])
                if len(batches) == 1:
                    batches[0]["quantity"] = updated
                # Multiple explicit dates require a human allocation of the increment.
            delta = updated - line["original_qty"]
            if updated != previous or not line.get("quantity_note"):
                line["quantity_note"] = (f"自动凑为5的倍数并按四仓合计尽量补至100；较原量{'增加' if delta >= 0 else '减少'}{abs(delta)}件"
                                     if delta else "")
            line["quantity_group_original"] = original
            line["quantity_group_updated"] = total
        if 0 < total < 100:
            warnings.append(f"{name}：四仓合计原订{original}件，调整后{total}件；遵守最多+30件，仍不足100件。")
    project["quantity_rules"] = True
    project["quantity_warnings"] = warnings
    return refresh_quantity_info(project)
