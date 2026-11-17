"""Bounded read-only OOXML reader. Never executes Excel/WPS formulas or macros."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ALIASES = {
    "code": ["product code", "item id", "productcode", "sku", "产品编码", "客户编码"],
    "oem": ["oem code", "oem", "oemcode"],
    "description": ["product description", "item name", "description", "产品名称", "品名"],
    "barcode": ["barcode no.", "barcode", "barcode no", "条码"],
    "cbm": ["cbm", "单件体积", "体积"],
    "weight": ["g.w", "g.w.", "gw", "毛重", "单件毛重"],
    "abc": ["class", "abc class", "abc", "等级"],
    "lsd": ["lsd", "发货日期", "交期"],
    "quantity": ["qty", "quantity", "数量", "total", "total units"],
    "warehouse": ["warehouse", "目的仓", "仓库"],
    "factory": ["factory", "工厂"],
    "usd": ["usd", "usd price"],
    "rmb": ["rmb", "人民币"],
    "supplier_code": ["supplier code", "供应商编码"],
    "supplier_name": ["supplier name", "供应商名称"],
    "category": ["category", "品类"],
    "sub_category": ["sub category", "subcategory", "子品类"],
    "status": ["status", "产品状态"],
}
WAREHOUSES = ["DCSYD", "DCBRI", "DCVIC", "DCFRE"]


def text(value):
    return "" if value is None else str(value).strip()


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", text(value)).upper().split())


def codekey(value):
    return normalized(value).replace(" ", "")


def number(value):
    try:
        raw = text(value)
        if "," in raw and not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
            return None
        n = Decimal(raw.replace(",", ""))
        return str(n) if n.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def integer(value):
    n = number(value)
    if n is None or Decimal(n) != Decimal(n).to_integral_value():
        return None
    return int(Decimal(n))


def letters(index):
    result = ""
    while index:
        index, rest = divmod(index - 1, 26)
        result = chr(65 + rest) + result
    return result


def column_number(column):
    result = 0
    for character in column:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def read_book(path: Path):
    if path.suffix.lower() == ".csv":
        data = path.read_bytes()
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = data.decode("gb18030")
        return {"CSV": [{"row": i, "cells": {letters(j): v for j, v in enumerate(r, 1) if v != ""}}
                        for i, r in enumerate(csv.reader(io.StringIO(content)), 1)]}
    if path.suffix.lower() != ".xlsx":
        raise ValueError("请导入 .xlsx 或 .csv；旧版 .xls 请先在 Excel 中另存为 .xlsx。")
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) > 20000 or sum(i.file_size for i in archive.infolist()) > 250_000_000:
            raise ValueError("工作簿解压后超过处理上限，请拆分文件。")
        strings = []
        if "xl/sharedStrings.xml" in names:
            strings = ["".join(t.text or "" for t in x.iter(f"{{{NS['s']}}}t"))
                       for x in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        relationships = {x.attrib["Id"]: x.attrib["Target"]
                         for x in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        sheets = ET.fromstring(archive.read("xl/workbook.xml")).find("s:sheets", NS)
        result = {}
        for sheet in sheets:
            target = relationships[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = []
            root = ET.fromstring(archive.read(target))
            for row in root.findall("s:sheetData/s:row", NS):
                cells = {}
                for c in row:
                    v = c.find("s:v", NS)
                    value = v.text if v is not None else None
                    if c.attrib.get("t") == "s" and value is not None:
                        value = strings[int(value)]
                    if c.attrib.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in c.findall(".//s:t", NS))
                    # No cached result means missing, never silently use zero.
                    if value is not None:
                        cells[re.sub(r"\d", "", c.attrib["r"])] = value
                if cells:
                    rows.append({"row": int(row.attrib["r"]), "cells": cells})
            # Preserve merged heading boundaries without filling or changing raw cells.
            by_row = {r["row"]: r for r in rows[:30]}
            for merged in root.findall("s:mergeCells/s:mergeCell", NS):
                match = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", merged.get("ref", ""))
                if not match or match[2] != match[4] or int(match[2]) not in by_row:
                    continue
                source = by_row[int(match[2])]
                value = source["cells"].get(match[1])
                if value:
                    source.setdefault("header_spans", []).append({"start": column_number(match[1]),
                        "end": column_number(match[3]), "value": value})
            result[sheet.attrib["name"]] = rows
        return result


def column_unit(rows, header, column):
    def classify(value):
        value = normalized(value)
        if re.search(r"\bCBM\b|\bM[³3]\b|体积|立方|\bVOLUME\b", value):
            return "volume"
        if re.search(r"\bQTY\b|\bQUANTITY\b|\bUNITS?\b|\bPCS\b|数量|件数", value):
            return "quantity"
        return ""

    direct = classify(header["cells"].get(column))
    if direct:
        return direct
    index = column_number(column)
    for row in reversed([r for r in rows[:30] if r["row"] < header["row"]]):
        spans = row.get("header_spans", [])
        covering = [s for s in spans if s["start"] <= index <= s["end"]]
        if covering:
            unit = classify(covering[-1]["value"])
        else:
            anchors = [(column_number(c), v) for c, v in row["cells"].items()
                       if column_number(c) <= index and not any(s["start"] == column_number(c) and s["end"] < index for s in spans)]
            unit = classify(max(anchors, default=(0, ""))[1])
        if unit:
            return unit
    return ""


def suggest(rows, header_row=None):
    if header_row is not None and (type(header_row) is not int or header_row < 1):
        raise ValueError("表头行必须为正整数。")
    def score(row):
        values = {normalized(v).lower() for v in row["cells"].values()}
        return (sum(bool(values.intersection(aliases)) for aliases in ALIASES.values())
                + sum(warehouse_header(v) is not None for v in values))
    header = (next((r for r in rows if r["row"] == header_row), {"row": header_row, "cells": {}})
              if header_row is not None else max(rows[:30], key=score) if rows else {"row": 1, "cells": {}})
    mapping = {}
    candidates = {w: [] for w in WAREHOUSES}
    units = {c: unit for c in header["cells"] if (unit := column_unit(rows, header, c))}
    for col, value in header["cells"].items():
        v = normalized(value).lower()
        for field, aliases in ALIASES.items():
            if v in aliases:
                mapping[field] = col
        warehouse = warehouse_header(value)
        if warehouse:
            if units.get(col) != "volume":
                candidates[warehouse].append(col)
    ambiguous = {}
    notes = []
    for warehouse, columns in candidates.items():
        explicit = [c for c in columns if units.get(c) == "quantity"]
        choices = explicit or columns
        if len(choices) == 1:
            mapping[warehouse] = choices[0]
            units.setdefault(choices[0], "quantity")
        elif len(choices) > 1:
            ambiguous[warehouse] = choices
            notes.append(f"{warehouse}有多个可能的数量列（{'、'.join(choices)}），请手动选择。")
    volumes = [c for c, u in units.items() if u == "volume" and warehouse_header(header["cells"][c])]
    if volumes:
        notes.insert(0, f"{'、'.join(volumes)}列属于CBM体积区，不作为订购件数；请核对下方仓库数量对应关系。")
    warehouse_cols = {mapping[w] for w in WAREHOUSES if mapping.get(w)}
    if warehouse_cols:
        mapping.pop("quantity", None)  # A wide table's total is not a long-table quantity.
    detail = [r for r in rows if r["row"] > header["row"] and
              (text(r["cells"].get(mapping.get("code", ""))) or text(r["cells"].get(mapping.get("description", ""))))]
    blanks = sum(not text(row["cells"].get(col)) for row in detail for col in warehouse_cols)
    order_layout = bool(mapping.get("description") and (warehouse_cols or ambiguous or (mapping.get("quantity") and mapping.get("warehouse"))))
    order_ready = order_layout and not bool(ambiguous)
    sheet_kind = "order" if order_layout else "catalog" if mapping.get("cbm") or mapping.get("weight") else "other" if rows else "empty"
    return {"header_row": header["row"], "mapping": mapping,
            "headers": header["cells"], "count": len(rows), "preview": rows[:8],
            "blank_warehouse_quantities": blanks, "column_units": units,
            "ambiguous_warehouses": ambiguous, "mapping_notes": notes, "order_ready": order_ready, "sheet_kind": sheet_kind}


def warehouse_header(value):
    compact = re.sub(r"[\s_.()\-]", "", normalized(value))
    for warehouse in WAREHOUSES:
        if compact in {warehouse, warehouse + "QTY", warehouse + "QUANTITY", warehouse + "数量"}:
            return warehouse
    return None


def parse_dates(value, year):
    raw = text(value)
    if not raw:
        return []
    if re.fullmatch(r"\d+(\.0+)?", raw) and 20000 < float(raw) < 80000:
        return [(date(1899, 12, 30) + timedelta(days=int(float(raw)))).isoformat()]
    matches = re.findall(r"\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{1,2}[/.-]\d{1,2}", raw)
    results = []
    for token in matches:
        parts = re.split(r"[/.-]", token)
        if len(parts) == 2:
            y, m, d = year, *parts
        elif len(parts[0]) == 4:
            y, m, d = parts
        else:
            first, second, y = parts
            if int(first) > 12 >= int(second):
                d, m = first, second
            elif int(second) > 12 >= int(first):
                m, d = first, second
            else:
                # 03/08/2026 is ambiguous: do not silently choose US/EU ordering.
                return []
        try:
            results.append(date(int(y or year), int(m), int(d)).isoformat())
        except ValueError:
            return []
    return sorted(set(results))
