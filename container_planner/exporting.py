from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
import math
import unicodedata

import xlsxwriter

from .solver import LIMITS, totals, validate
from .service import FACTORY_ORDER


def original_allocations(plan):
    """Allocate source quantities proportionally, preserving integer source totals."""
    atoms = {a["id"]: a for a in plan["snapshot"]["atoms"]}
    lines = {l["id"]: l for l in plan["snapshot"]["project"]["lines"]}
    rows = defaultdict(list)
    for ci, c in enumerate(plan["containers"]):
        for ri, r in enumerate(c["allocations"]):
            rows[atoms[r["atom_id"]]["line_id"]].append(((ci, ri), r["quantity"]))
    result = {}
    for line_id, parts in rows.items():
        original = lines[line_id]["original_qty"]
        total = sum(q for _, q in parts)
        fractions = [(key, Decimal(original) * q / total) for key, q in parts]
        for key, value in fractions:
            result[key] = int(value.to_integral_value(rounding=ROUND_FLOOR))
        remainder = original - sum(result[key] for key, _ in fractions)
        ranked = sorted(fractions, key=lambda kv: kv[1] - int(kv[1]), reverse=True)
        for key, _ in ranked[:remainder]:
            result[key] += 1
    return result


def export_plan(plan, path: Path):
    errors = validate(plan["containers"], plan["snapshot"]["atoms"])
    if errors:
        raise ValueError("禁止导出未通过校验的方案：" + "；".join(errors))
    atoms = {a["id"]: a for a in plan["snapshot"]["atoms"]}
    products = {p["id"]: p for p in plan["snapshot"]["products"]}
    source_qty = original_allocations(plan)
    wb = xlsxwriter.Workbook(str(path), {"strings_to_formulas": False, "strings_to_urls": False})
    wb.set_properties({"title": plan["name"], "subject": "按工厂、目的仓和发货批次排柜", "author": "Container Planner"})
    base = {"font_name": "Arial", "font_size": 10, "valign": "vcenter"}
    header = wb.add_format({**base, "bg_color": "#243D50", "font_color": "white", "bold": True, "align": "center", "text_wrap": True})
    body = wb.add_format(base)
    wrapped = wb.add_format({**base, "text_wrap": True})
    identifier = wb.add_format({**base, "num_format": "@"})
    num = wb.add_format({**base, "num_format": "#,##0"})
    decimal = wb.add_format({**base, "num_format": "0.00000000"})
    kg = wb.add_format({**base, "num_format": "#,##0.00"})
    title = wb.add_format({**base, "font_size": 14, "bold": True})
    group = wb.add_format({**base, "bg_color": "#E6EEF2", "bold": True})
    total = wb.add_format({**base, "bold": True, "top": 1, "num_format": "#,##0.00000000"})
    total_kg = wb.add_format({**base, "bold": True, "top": 1, "num_format": "#,##0.00"})
    note = wb.add_format({**base, "font_color": "#5A6570", "text_wrap": True})
    detail = wb.add_worksheet("排柜明细")
    detail.hide_gridlines(2)
    detail.set_landscape()
    detail.set_paper(8)
    detail.fit_to_pages(1, 0)
    detail.repeat_rows(0, 1)
    detail.freeze_panes(2, 4)
    widths = [10, 8, 26, 26, 58, 20, 13, 13, 16, 13, 17, 16, 12, 15]
    for i, width in enumerate(widths):
        detail.set_column(i, i, width)
    detail.merge_range(0, 0, 0, 13, plan["name"] + ("（部分LSD待填写）" if any(not c.get("date") for c in plan["containers"]) else ""), title)
    detail.set_row(0, 28)
    columns = ["PO NO.", "CLASS", "PRODUCT CODE", "OEM CODE", "Product Description", "Barcode NO.",
               "Original Qty", "Updated Qty", "CBM", "G.W", "Total CBM", "Total G.W.", "Cont Size", "LSD"]
    detail.write_row(1, 0, columns, header)
    detail.set_row(1, 30)
    row = 2
    previous = None
    all_v, all_w = Decimal(0), Decimal(0)
    for ci, c in enumerate(plan["containers"]):
        key = c["factory"], c["warehouse"], c["date"], c.get("load_class", "REGULAR")
        if key != previous:
            detail.merge_range(row, 0, row, 13, f"{key[0]}   /   {key[1]}   /   LSD {key[2] or '待填写'}   /   {'新品NEW' if key[3]=='NEW' else '常规品'}", group)
            detail.set_row(row, 25)
            row += 1
            previous = key
        first = row
        for ri, allocation in enumerate(c["allocations"]):
            a = atoms[allocation["atom_id"]]
            q = allocation["quantity"]
            detail.write_row(row, 0, [c["number"] if ri == 0 else "", a["abc"], a["code"], a["oem"], a["description"], a["barcode"]], body)
            detail.write(row, 4, a["description"], wrapped)
            for col, field in ((2, "code"), (3, "oem"), (5, "barcode")):
                detail.write_string(row, col, str(a[field]), identifier)
            detail.write_number(row, 6, source_qty[ci, ri], num)
            detail.write_number(row, 7, q, num)
            detail.write_number(row, 8, float(a["cbm"]), decimal)
            detail.write_number(row, 9, float(a["weight"]), kg)
            detail.write_formula(row, 10, f"=H{row+1}*I{row+1}", decimal, float(Decimal(a["cbm"]) * q))
            detail.write_formula(row, 11, f"=H{row+1}*J{row+1}", kg, float(Decimal(a["weight"]) * q))
            detail.write(row, 12, f"1×{c['type']}" if ri == 0 else "", body)
            detail.write(row, 13, c["date"] if ri == 0 else "", body)
            display_length = sum(2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1 for ch in a["description"])
            detail.set_row(row, max(22, 14 * math.ceil(display_length / 55) + 8))
            row += 1
        v, w = totals(c, atoms)
        detail.merge_range(row, 0, row, 9, "TOTAL", total)
        detail.write_formula(row, 10, f"=SUM(K{first+1}:K{row})", total, float(v))
        detail.write_formula(row, 11, f"=SUM(L{first+1}:L{row})", total_kg, float(w))
        detail.write(row, 12, f"≤{LIMITS[c['type']]['cbm']}m³", note)
        detail.write(row, 13, "≤22,800kg", note)
        all_v += v
        all_w += w
        row += 2
    detail.merge_range(row, 0, row, 9, f"共 {len(plan['containers'])} 柜", total)
    detail.write_number(row, 10, float(all_v), total)
    detail.write_number(row, 11, float(all_w), total_kg)
    detail.print_area(0, 0, row, 13)
    detail.set_footer("第 &P / &N 页")
    summary = wb.add_worksheet("Summary")
    summary.hide_gridlines(2)
    summary.freeze_panes(2, 3)
    summary.set_landscape()
    summary.fit_to_pages(1, 0)
    summary.set_paper(8)
    warehouses = list(dict.fromkeys(["DCSYD", "DCBRI", "DCVIC", "DCFRE"] + [a["warehouse"] for a in atoms.values()]))
    headings = ["工厂", "PRODUCT CODE", "Item Name", "ABC Class", *warehouses, "Total", "LSD", "Original Qty", "Difference"]
    summary.merge_range(0, 0, 0, len(headings)-1, "订单与排柜数量汇总", title)
    summary.set_row(0, 28)
    summary.write_row(1, 0, headings, header)
    summary.set_row(1, 30)
    summary.set_column(0, 0, 12)
    summary.set_column(1, 1, 26)
    summary.set_column(2, 2, 58)
    summary.set_column(3, len(headings)-1, 15)
    summary.set_column(5 + len(warehouses), 5 + len(warehouses), 32)
    aggregated = {}
    excluded = []
    for line in plan["snapshot"]["project"]["lines"]:
        if line.get("excluded"):
            excluded.append(line)
            continue
        p = products[line["product_id"]]
        key = p["id"]
        if key not in aggregated:
            aggregated[key] = {"p": p, "warehouses": defaultdict(int), "original": 0, "dates": set(), "abc": set()}
        entry = aggregated[key]
        entry["warehouses"][line["warehouse"]] += line["updated_qty"]
        entry["original"] += line["original_qty"]
        entry["dates"].update(b["date"] for b in line["batches"])
        if line.get("abc"):
            entry["abc"].add(line["abc"])
    for c in plan["containers"]:
        if c.get("date"):
            for row in c["allocations"]:
                aggregated[atoms[row["atom_id"]]["product_id"]]["dates"].add(c["date"])
    ordered = sorted(aggregated.values(), key=lambda e: (
        FACTORY_ORDER.index(e["p"]["factory"]) if e["p"]["factory"] in FACTORY_ORDER else 100, e["p"]["factory"]))
    for sr, entry in enumerate(ordered, 2):
        p = entry["p"]
        summary.write_row(sr, 0, [p["factory"], p.get("code", ""), p["description"], ", ".join(sorted(entry["abc"]))], body)
        summary.write(sr, 2, p["description"], wrapped)
        summary.write_string(sr, 1, str(p.get("code", "")), identifier)
        values = [entry["warehouses"][w] for w in warehouses]
        summary.write_row(sr, 4, values, num)
        total_col = 4 + len(warehouses)
        from .excel import letters
        summary.write_formula(sr, total_col, f"=SUM(E{sr+1}:{letters(total_col)}{sr+1})", num, sum(values))
        dates = sorted(entry["dates"])
        summary.write(sr, total_col + 1, "\n".join("、".join(dates[i:i+2]) for i in range(0, len(dates), 2)), wrapped)
        summary.write_number(sr, total_col + 2, entry["original"], num)
        summary.write_formula(sr, total_col + 3, f"={letters(total_col+1)}{sr+1}-{letters(total_col+3)}{sr+1}", num, sum(values)-entry["original"])
        summary.set_row(sr, max(24, 14 * math.ceil(len(p["description"]) / 55) + 8, 14 * math.ceil(len(entry["dates"]) / 2) + 8))
    if aggregated:
        summary.autofilter(1, 0, len(aggregated)+1, len(headings)-1)
        sr = len(aggregated) + 2
        summary.merge_range(sr, 0, sr, 3, "TOTAL", total)
        total_col = 4 + len(warehouses)
        for col in [*range(4, total_col + 1), total_col + 2, total_col + 3]:
            expected = sum(entry["warehouses"][warehouses[col-4]] for entry in aggregated.values()) if col < total_col else (
                sum(sum(e["warehouses"].values()) for e in aggregated.values()) if col == total_col else
                sum(e["original"] for e in aggregated.values()) if col == total_col+2 else
                sum(sum(e["warehouses"].values())-e["original"] for e in aggregated.values()))
            summary.write_formula(sr, col, f"=SUM({letters(col+1)}3:{letters(col+1)}{sr})", num, expected)
    summary.repeat_rows(0, 1)
    changed_lines = [l for l in plan["snapshot"]["project"]["lines"] if not l.get("excluded") and l.get("original_qty") != l.get("updated_qty")]
    warnings = plan["snapshot"]["project"].get("quantity_warnings", [])
    if changed_lines or warnings:
        changes = wb.add_worksheet("数量调整")
        changes.hide_gridlines(2)
        changes.write_row(0, 0, ["产品编码", "产品名称", "目的仓", "原数量", "排柜数量", "增减量", "调整原因", "四仓原合计", "四仓调整合计"], header)
        changes.set_column(0, 0, 26); changes.set_column(1, 1, 55); changes.set_column(2, 5, 15)
        changes.set_column(6, 6, 65); changes.set_column(7, 8, 18)
        for r, line in enumerate(changed_lines, 1):
            changes.write_row(r, 0, [line["source_code"], line["description"], line["warehouse"], line["original_qty"], line["updated_qty"],
                                   line["updated_qty"]-line["original_qty"], line.get("quantity_note") or "人工调整",
                                   line.get("quantity_group_original"), line.get("quantity_group_updated")], wrapped)
            changes.set_row(r, 36)
        for r, message in enumerate(warnings, len(changed_lines)+2):
            changes.merge_range(r, 0, r, 8, message, wrapped); changes.set_row(r, 30)
        changes.freeze_panes(1, 2)
    if excluded:
        skipped = wb.add_worksheet("未参与订单")
        skipped.hide_gridlines(2)
        skipped.write_row(0, 0, ["原产品编码", "产品名称", "目的仓", "原数量", "调整数量", "LSD", "排除原因", "原文件", "工作表", "原行号"], header)
        skipped.set_column(0, 0, 26)
        skipped.set_column(1, 1, 58)
        skipped.set_column(2, 5, 16)
        skipped.set_column(6, 6, 48)
        skipped.set_column(7, 7, 60)
        skipped.set_column(8, 8, 24)
        for r, line in enumerate(excluded, 1):
            source = line.get("source", {})
            skipped.write_row(r, 0, [line["source_code"], line["description"], line["warehouse"], line["original_qty"],
                                    line["updated_qty"], line["lsd"].replace("、", "\n"), line["exclusion_reason"], source.get("file", ""),
                                    source.get("sheet", ""), source.get("row", "")], wrapped)
            lengths = [(line["description"], 55), (line["lsd"], 16), (line["exclusion_reason"], 45), (source.get("file", ""), 57)]
            display_lines = max(math.ceil(sum(2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1 for ch in value) / width) for value, width in lengths)
            skipped.set_row(r, max(24, display_lines * 14 + 8))
        skipped.freeze_panes(1, 2)
    wb.close()
    return path
