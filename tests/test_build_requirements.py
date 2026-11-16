from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
import pytest

from scripts import build_windows_portable as builder


@pytest.mark.parametrize("host", ["darwin", "win32"])
def test_portable_dependencies_use_embedded_python_not_build_host(monkeypatch, host):
    environment = {**default_environment(), "sys_platform": host, "python_version": "3.11"}
    monkeypatch.setattr(builder, "default_environment", lambda: environment)
    selected = [Requirement(value) for value in builder.target_requirements()]
    runtime = [req for req in selected if req.name == "msvc-runtime"]
    assert len(runtime) == 1
    assert str(runtime[0].specifier) == "==14.51.36231"
    assert all(req.marker is None for req in selected)  # pip must not re-evaluate against its host


@pytest.mark.parametrize("version,runtime", [("3.11", "14.44.35112"), ("3.13", "14.51.36231")])
def test_windows_source_and_embedded_pythons_each_select_one_available_runtime(version, runtime):
    environment = {**default_environment(), "sys_platform": "win32", "python_version": version}
    lines = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text().splitlines()
    matches = [req for line in lines if line.startswith("msvc-runtime")
               for req in [Requirement(line)] if req.marker.evaluate(environment)]
    assert len(matches) == 1
    assert runtime in matches[0].specifier
