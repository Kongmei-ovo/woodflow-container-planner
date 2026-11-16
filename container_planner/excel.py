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
    "quantity": ["qty", "quantity", "数量", "total"],
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
            result[sheet.attrib["name"]] = rows
        return result


def suggest(rows):
    def score(row):
        values = {normalized(v).lower() for v in row["cells"].values()}
        return (sum(bool(values.intersection(aliases)) for aliases in ALIASES.values())
                + sum(warehouse_header(v) is not None for v in values))
    header = max(rows[:30], key=score) if rows else {"row": 1, "cells": {}}
    mapping = {}
    for col, value in header["cells"].items():
        v = normalized(value).lower()
        for field, aliases in ALIASES.items():
            if v in aliases:
                mapping[field] = col
        warehouse = warehouse_header(value)
        if warehouse:
            mapping[warehouse] = col
    warehouse_cols = {mapping[w] for w in WAREHOUSES if mapping.get(w)}
    detail = [r for r in rows if r["row"] > header["row"] and
              (text(r["cells"].get(mapping.get("code", ""))) or text(r["cells"].get(mapping.get("description", ""))))]
    blanks = sum(not text(row["cells"].get(col)) for row in detail for col in warehouse_cols)
    return {"header_row": header["row"], "mapping": mapping,
            "headers": header["cells"], "count": len(rows), "preview": rows[:8],
            "blank_warehouse_quantities": blanks}


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
