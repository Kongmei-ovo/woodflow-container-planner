from __future__ import annotations

import copy
from collections import defaultdict
from decimal import Decimal
from difflib import SequenceMatcher

from .excel import WAREHOUSES, codekey, integer, normalized, number, parse_dates, read_book, suggest, text
from .store import uid

PLACEHOLDERS = {"NOSKUSYET", "SKUNOTCREATED", "NONE", "N/A", "TBC", "待定"}
FACTORY_ORDER = ["利泰", "续泰", "好事达"]


def valid_code(value):
    return bool(codekey(value)) and codekey(value) not in PLACEHOLDERS


def product_index(products):
    indices = {field: defaultdict(list) for field in ("code", "oem", "barcode")}
    for p in products:
        for field, index in indices.items():
            if valid_code(p.get(field)):
                index[codekey(p[field])].append(p)
    return indices


def matches(fields, indices):
    for field in ("code", "oem", "barcode"):
        if valid_code(fields.get(field)):
            found = indices[field].get(codekey(fields[field]), [])
            if found:
                return found
    return []


def candidates(description, products):
    name = normalized(description)
    if not name:
        return []
    scored = [(SequenceMatcher(None, name, normalized(p.get("description"))).ratio(), p)
              for p in products]
    return [{"id": p["id"], "code": p.get("code", ""), "description": p.get("description", ""),
             "factory": p.get("factory", "")} for score, p in sorted(scored, key=lambda s: s[0], reverse=True)[:5]
            if score >= .55]


def mapped(row, mapping):
    return {field: row["cells"].get(col, "") for field, col in mapping.items() if col}


def commit_import(store, imp, config):
    if imp.get("status") == "committed":
        raise ValueError("该文件已经导入，请勿重复提交。")
    book = read_book(store.root / "originals" / imp["stored_name"])
    kind = config.get("kind", "order")
    if kind not in {"catalog", "factory", "prices", "order"}:
        raise ValueError("不支持的资料类型。")
    selected = config.get("sheet") or next(iter(book))
    if selected not in book:
        raise ValueError("工作表不存在。")
    sheets = list(book) if kind == "factory" and config.get("all_sheets", True) else [selected]
    products = store.list("product")
    indices = product_index(products)
    changed = {}
    diagnostics = []
    source_rows = []
    year = config.get("year", 2026)
    if not isinstance(year, int) or not 1900 <= year <= 2200:
        raise ValueError("请提供正确的四位年份。")
    batch_date = text(config.get("default_batch_date"))
    if batch_date:
        from datetime import date
        if date.fromisoformat(batch_date).isoformat() != batch_date:
            raise ValueError("统一发货日期须为YYYY-MM-DD。")
    blank_as_zero = config.get("blank_quantity_as_zero", False)
    if type(blank_as_zero) is not bool:
        raise ValueError("请明确确认空白仓库数量是否按0处理。")
    for sheet in sheets:
        auto = suggest(book[sheet])
        header_row = config.get("header_row", auto["header_row"]) if sheet == selected else auto["header_row"]
        mapping = config.get("mapping") or auto["mapping"]
        if sheet != selected:
            mapping = auto["mapping"]
        needed = {"catalog": ["description"], "factory": ["description"],
                  "prices": ["oem"], "order": ["description"]}[kind]
        if any(not mapping.get(f) for f in needed):
            raise ValueError(f"{sheet}：请对应必要字段：{'、'.join(needed)}。")
        if kind == "order" and not (any(mapping.get(w) for w in WAREHOUSES)
                                     or (mapping.get("quantity") and mapping.get("warehouse"))):
            raise ValueError("请对应至少一个目的仓数量列，或对应‘数量’和‘目的仓’两列。")
        for row in book[sheet]:
            if row["row"] <= header_row:
                continue
            fields = mapped(row, mapping)
            name = text(fields.get("description"))
            code = text(fields.get("code"))
            if not name and not valid_code(code):
                continue
            if ("合计" in code or "总计" in code or code.startswith("◆")
                    or normalized(code) in {"TOTAL", "TOTAL：", "PRODUCT CODE", "ITEM ID"}):
                continue
            source = {"import_id": imp["id"], "file": imp["filename"], "sheet": sheet,
                      "row": row["row"], "values": fields}
            source_rows.append(source)
            if kind == "order":
                continue
            found = matches(fields, indices)
            if kind == "catalog":
                # Customer SKU is the catalog identity. Shared OEM/barcode values
                # must not collapse distinct sellable products into one record.
                if valid_code(code):
                    found = indices["code"].get(codekey(code), [])
                if not (valid_code(code) or valid_code(fields.get("oem"))):
                    diagnostics.append({**source, "message": "缺少产品编码/OEM，未自动建立产品"})
                    continue
                if len(found) > 1:
                    diagnostics.append({**source, "message": "编码存在多条匹配，需人工审核"})
                    continue
                p = copy.deepcopy(changed.get(found[0]["id"], found[0])) if found else {
                    "id": uid(), "code": code, "oem": text(fields.get("oem")),
                    "barcode": text(fields.get("barcode")), "description": name,
                    "factory": "", "factory_candidates": [], "cbm": number(fields.get("cbm")),
                    "weight": number(fields.get("weight")), "conflicts": [], "sources": []}
                if found:
                    for field in ("cbm", "weight"):
                        value = number(fields.get(field))
                        if value is not None and p.get(field) is not None and Decimal(value) != Decimal(p[field]):
                            p.setdefault("conflicts", []).append(f"{field}资料冲突：现值{p[field]}，新值{value}")
                        elif p.get(field) is None:
                            p[field] = value
                p["sources"].append(source)
                changed[p["id"]] = p
                if not found:
                    products.append(p)
                    for field in indices:
                        if valid_code(p.get(field)):
                            indices[field][codekey(p[field])].append(p)
            elif kind == "factory":
                if len(found) != 1:
                    diagnostics.append({**source, "message": "未通过编码唯一匹配，请在产品资料中人工确认",
                                        "candidates": candidates(name, products)})
                    continue
                p = copy.deepcopy(changed.get(found[0]["id"], found[0]))
                factory = text(fields.get("factory")) or sheet
                # Preserve all candidate factories; never overwrite a conflict with the last row.
                choices = set(p.get("factory_candidates", [])) | {factory}
                if p.get("factory"):
                    choices.add(p["factory"])
                p["factory_candidates"] = sorted(choices)
                p["factory"] = next(iter(choices)) if len(choices) == 1 else ""
                fw = number(fields.get("weight"))
                if fw and p.get("weight") and Decimal(fw) != Decimal(p["weight"]):
                    p.setdefault("warnings", []).append(f"工厂表毛重{fw}kg；按已确认规则保留排柜资料{p['weight']}kg")
                p.setdefault("sources", []).append(source)
                changed[p["id"]] = p
            elif kind == "prices":
                if len(found) != 1:
                    diagnostics.append({**source, "message": "价格未找到唯一产品，不影响排柜"})
                    continue
                p = copy.deepcopy(changed.get(found[0]["id"], found[0]))
                p["usd"], p["rmb"] = number(fields.get("usd")), number(fields.get("rmb"))
                p.setdefault("sources", []).append(source)
                changed[p["id"]] = p
    items = [("product", p, id, p.get("revision"), f"导入{kind}") for id, p in changed.items()]
    project = None
    if kind == "order":
        lines = []
        for source in source_rows:
            f = source["values"]
            found = matches(f, indices)
            product_id = found[0]["id"] if len(found) == 1 else None
            warehouses = [(w, f[w]) for w in WAREHOUSES if w in f]
            if not warehouses:
                warehouses = [(text(f.get("warehouse")), f.get("quantity"))]
            dates = parse_dates(f.get("lsd"), year)
            if not text(f.get("lsd")) and batch_date:
                dates = [batch_date]
            for warehouse, value in warehouses:
                quantity = 0 if blank_as_zero and not text(value) else integer(value)
                if quantity == 0:
                    continue
                lines.append({"id": uid(), "product_id": product_id, "source_code": text(f.get("code")),
                              "description": text(f.get("description")), "abc": text(f.get("abc")),
                              "warehouse": warehouse, "original_qty": quantity, "updated_qty": quantity,
                              "lsd": text(f.get("lsd")), "suggested_dates": dates,
                              "date_source": "导入时人工指定" if not text(f.get("lsd")) and batch_date else "原订单",
                              **{key: text(f.get(key)) for key in ("supplier_code", "supplier_name", "category", "sub_category", "status") if key in f},
                              "batches": [{"date": dates[0], "quantity": quantity}] if len(dates) == 1 and quantity is not None else [],
                              "excluded": False, "exclusion_reason": "", "source": source})
        if not lines:
            raise ValueError("没有识别到非零订单数量，请检查表头和字段对应关系。")
        project = {"id": uid(), "name": text(config.get("project_name")) or imp["filename"].rsplit(".", 1)[0],
                   "import_id": imp["id"], "lines": lines,
                   "allow_undated": bool(config.get("allow_undated", False))}
        if config.get("auto_adjust", False):
            from .quantities import adjust_quantities
            adjust_quantities(project)
        items.append(("project", project, project["id"], None, "导入订单"))
    imp = {**imp, "status": "committed", "kind": kind, "config": config, "diagnostics": diagnostics,
           "project_id": project["id"] if project else None, "processed": len(source_rows), "updated_products": len(changed)}
    items.append(("import", imp, imp["id"], imp["revision"], "完成导入"))
    signature = f"{kind}:{selected}"
    old = next((m for m in store.list("mapping") if m.get("signature") == signature), None)
    items.append(("mapping", {"signature": signature, "config": config}, old["id"] if old else None,
                  old["revision"] if old else None, "记住字段映射"))
    store.put_many(items)
    return {"import_id": imp["id"], "project_id": imp.get("project_id"), "processed": len(source_rows),
            "updated_products": len(changed), "diagnostics": len(diagnostics)}


def product_issues(p):
    result = []
    if not p.get("factory"):
        result.append("工厂待确认" if not p.get("factory_candidates") else "工厂归属待确认")
    for field, title in (("cbm", "单件体积"), ("weight", "单件毛重")):
        value = number(p.get(field))
        if value is None or Decimal(value) <= 0:
            result.append(f"{title}须为正数")
    result.extend(p.get("conflicts", []))
    return result


def line_issues(line, products, allow_undated=False, quantity_rules=False):
    if line.get("excluded"):
        return [] if text(line.get("exclusion_reason")) else ["排除订单必须填写原因"]
    result = []
    if line.get("original_qty") is None:
        result.append("原始数量无法识别，请核实后补录")
    quantity = line.get("updated_qty")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
        result.append("排柜数量须为非负整数")
    elif quantity_rules and quantity % 5:
        result.append("排柜数量须以5或0结尾，请自动凑整或手动修改")
    if not line.get("warehouse"):
        result.append("目的仓缺失")
    p = products.get(line.get("product_id"))
    if not p:
        result.append("产品未绑定")
    else:
        result += product_issues(p)
    batches = line.get("batches", [])
    if not batches and quantity != 0 and (not allow_undated or text(line.get("lsd"))):
        result.append("发货批次待分配")
    valid = True
    dates = set()
    for batch in batches:
        d = text(batch.get("date"))
        try:
            from datetime import date
            parsed = date.fromisoformat(d)
            if parsed.isoformat() != d:
                raise ValueError()
        except ValueError:
            result.append("批次日期须为YYYY-MM-DD")
        if d in dates:
            result.append("同一行有重复批次，请合并数量")
        dates.add(d)
        q = batch.get("quantity")
        if not isinstance(q, int) or isinstance(q, bool) or q <= 0:
            result.append("批次数量须为正整数")
            valid = False
    if batches and valid and isinstance(quantity, int) and sum(b["quantity"] for b in batches) != quantity:
        result.append("各批次数量之和与排柜数量不符")
    return list(dict.fromkeys(result))


def project_view(store, project):
    from .quantities import refresh_quantity_info
    products = {p["id"]: p for p in store.list("product")}
    result = copy.deepcopy(project)
    refresh_quantity_info(result)
    result["lines"] = [{**l, "product": products.get(l.get("product_id")), "issues": line_issues(l, products, project.get("allow_undated", False), project.get("quantity_rules", False))}
                       for l in result["lines"]]
    result["issue_count"] = sum(bool(l["issues"]) for l in result["lines"])
    return result


def snapshot_inputs(project, products):
    from .quantities import refresh_quantity_info
    project = refresh_quantity_info(copy.deepcopy(project))
    by_id = {p["id"]: p for p in products}
    issues = [{"line_id": l["id"], "description": l["description"], "messages": line_issues(l, by_id, project.get("allow_undated", False), project.get("quantity_rules", False))}
              for l in project["lines"] if line_issues(l, by_id, project.get("allow_undated", False), project.get("quantity_rules", False))]
    if issues:
        raise ValueError(f"还有{len(issues)}行待审核，请先修正或填写原因后排除。")
    atoms = []
    for line in project["lines"]:
        if line.get("excluded") or not line["updated_qty"]:
            continue
        p = by_id[line["product_id"]]
        batches = line["batches"] or ([{"date": "", "quantity": line["updated_qty"]}] if project.get("allow_undated") else [])
        for i, batch in enumerate(batches):
            atoms.append({"id": f"{line['id']}:{i}", "line_id": line["id"], "product_id": p["id"],
                          "factory": p["factory"], "warehouse": line["warehouse"], "date": batch["date"],
                          "quantity": batch["quantity"], "cbm": p["cbm"], "weight": p["weight"],
                          "code": p.get("code", ""), "oem": p.get("oem", ""), "barcode": p.get("barcode", ""),
                          "description": p["description"], "abc": line.get("abc", ""),
                          "load_class": "NEW" if normalized(line.get("status")) == "NEW" else "REGULAR"})
    if not atoms:
        raise ValueError("本次没有需要排柜的货物。")
    return {"project": copy.deepcopy(project), "products": copy.deepcopy(products), "atoms": atoms}
