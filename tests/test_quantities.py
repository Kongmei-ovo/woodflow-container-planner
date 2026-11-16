from copy import deepcopy
import pytest
from container_planner.quantities import adjust_quantities, refresh_quantity_info
from container_planner.service import line_issues


def project(*quantities):
    return {"lines": [{"id": str(i), "product_id": "sku", "source_code": "SKU", "description": "桌子",
                      "warehouse": str(i), "original_qty": q, "updated_qty": q, "batches": []}
                     for i, q in enumerate(quantities)]}


@pytest.mark.parametrize("original,expected", [(49,75),(40,70),(50,80),(80,100),(101,105),(1000,1000)])
def test_rounding_and_minimum_never_exceed_original_plus_30(original, expected):
    p = adjust_quantities(project(original, 0, 0, 0))
    assert [l["updated_qty"] for l in p["lines"]] == [expected,0,0,0]
    assert p["lines"][0]["original_qty"] == original
    assert expected <= original+30
    assert bool(p["quantity_warnings"]) == (expected < 100)
    again = deepcopy(p)
    assert adjust_quantities(again) == p


def test_distribution_only_uses_existing_positive_ports_and_refreshes_after_edit():
    p = adjust_quantities(project(11, 28, 0, 0))
    assert sum(l["updated_qty"] for l in p["lines"]) == 65
    assert all(l["updated_qty"] % 5 == 0 for l in p["lines"])
    assert p["lines"][2]["updated_qty"] == p["lines"][3]["updated_qty"] == 0
    p["lines"][0]["updated_qty"] += 5
    refresh_quantity_info(p)
    assert all(l["quantity_group_updated"] == 70 for l in p["lines"])
    assert any("超过" in w for w in p["quantity_warnings"])
    manual = project(100)
    manual["lines"][0].update(updated_qty=105, quantity_note="人工调整；较原量变化5件")
    adjust_quantities(manual)
    assert manual["lines"][0]["quantity_note"].startswith("人工调整")


def test_explicit_multiple_dates_require_review_of_increment():
    p = project(49)
    p["lines"][0]["batches"] = [{"date":"2026-11-20","quantity":20},{"date":"2026-11-27","quantity":29}]
    adjust_quantities(p)
    assert sum(b["quantity"] for b in p["lines"][0]["batches"]) == 49
    assert "各批次数量之和与排柜数量不符" in line_issues(p["lines"][0], {}, True, True)
