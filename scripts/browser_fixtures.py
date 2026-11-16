"""Create synthetic files exclusively for the disposable browser acceptance test."""
from pathlib import Path
import xlsxwriter


def create(root):
    root.mkdir(parents=True, exist_ok=True)

    def write(name, sheets):
        with xlsxwriter.Workbook(str(root / name)) as workbook:
            for name, rows in sheets.items():
                sheet = workbook.add_worksheet(name)
                for i, row in enumerate(rows):
                    sheet.write_row(i, 0, row)

    write("catalog.xlsx", {"产品": [["PRODUCT CODE", "OEM CODE", "Product Description", "Barcode NO.", "CBM", "G.W"],
                               ["A", "OEM-A", "TEST BEDSIDE A", "00123", .1, 10],
                               ["B", "OEM-B", "TEST DESK B", "00124", .1, 10],
                               ["C", "OEM-C", "TEST CABINET C", "00125", .1, 10]]})
    write("factory.xlsx", {f: [["Product code", "Product Description"], [c, "TEST PRODUCT " + c]]
                           for f, c in [("利泰", "A"), ("续泰", "B"), ("好事达", "C")]})
    write("order.xlsx", {"订单": [["Item ID", "Item Name", "ABC Class", "DCSYD", "DCBRI", "DCVIC", "DCFRE", "LSD"],
                             ["A", "TEST BEDSIDE A", "A", 700, 0, 0, 0, "2026/12/21、2026/12/28"],
                             ["B", "TEST DESK B", "B", 400, 0, 0, 0, "2026/12/21"],
                             ["C", "TEST CABINET C", "A", 0, 100, 0, 0, "2026/12/21"]]})


if __name__ == "__main__":
    create(Path(__file__).resolve().parent.parent / ".local-data" / "browser-fixtures")
