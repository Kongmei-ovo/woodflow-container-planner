"""Synthetic onboarding data. No customer workbooks are bundled."""
from pathlib import Path
import shutil
import tempfile
import xlsxwriter
from .excel import read_book, suggest
from .service import commit_import
from .store import uid


def load_demo(store):
    if store.list("product") or store.list("project"):
        raise ValueError("练习示例仅可载入空白工作空间，已有业务资料不会被覆盖。")
    samples = [
        ("练习产品.xlsx", "catalog", {"产品": [
            ["PRODUCT CODE", "OEM CODE", "Product Description", "CBM", "G.W"],
            ["DEMO-A", "DEMO-OEM-A", "练习床头柜", .1, 10],
            ["DEMO-B", "DEMO-OEM-B", "练习书桌", .1, 10],
            ["DEMO-C", "DEMO-OEM-C", "练习储物柜", .1, 10]]}),
        ("练习工厂.xlsx", "factory", {name: [["Product code", "Product Description"], [code, desc]] for name, code, desc in [
            ("利泰", "DEMO-A", "练习床头柜"), ("续泰", "DEMO-B", "练习书桌"), ("好事达", "DEMO-C", "练习储物柜")]}),
        ("练习订单.xlsx", "order", {"订单": [
            ["Item ID", "Item Name", "ABC Class", "DCSYD", "DCBRI", "DCVIC", "DCFRE", "LSD"],
            ["DEMO-A", "练习床头柜", "A", 700, 0, 0, 0, "2027/01/11、2027/01/18"],
            ["DEMO-B", "练习书桌", "B", 400, 0, 0, 0, "2027/01/11"],
            ["DEMO-C", "练习储物柜", "A", 0, 100, 0, 0, "2027/01/11"]]}),
    ]
    result = None
    with tempfile.TemporaryDirectory() as tmp:
        for filename, kind, sheets in samples:
            path = Path(tmp) / filename
            with xlsxwriter.Workbook(str(path)) as workbook:
                for name, rows in sheets.items():
                    sheet = workbook.add_worksheet(name)
                    for i, row in enumerate(rows):
                        sheet.write_row(i, 0, row)
            id = uid()
            stored = id + ".xlsx"
            shutil.copyfile(path, store.root / "originals" / stored)
            views = {name: suggest(rows) for name, rows in read_book(path).items()}
            imp = store.put("import", {"filename": filename, "stored_name": stored, "status": "staged", "sheets": views}, id)
            name = next(iter(views))
            result = commit_import(store, imp, {"kind": kind, "sheet": name, "header_row": 1,
                "mapping": views[name]["mapping"], "project_name": "【练习】三家工厂排柜示例", "year": 2027})
    return {"project_id": result["project_id"]}
