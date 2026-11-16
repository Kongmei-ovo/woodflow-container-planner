from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from container_planner.api import create_app
from container_planner.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "app")) as client:
        yield client


def make_atom(id="a", product_id="p", q=100, cbm="0.1", weight="10", factory="利泰", warehouse="DCSYD", day="2026-12-21"):
    return {"id": id, "line_id": id, "product_id": product_id, "code": product_id, "oem": "OEM"+product_id,
            "barcode": "0123456789012", "description": "测试产品"+product_id, "abc": "A", "quantity": q,
            "cbm": cbm, "weight": weight, "factory": factory, "warehouse": warehouse, "date": day}
