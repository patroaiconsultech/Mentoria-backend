"""Strict checks for the mentoria disposable PostgreSQL CI gate."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "mentoria_pg_gate.py"
spec = importlib.util.spec_from_file_location("mentoria_pg_gate", FILE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _configure(monkeypatch, database="mentoria_ci_m2b_test", host="127.0.0.1"):
    url = f"postgresql+psycopg://mentoria_ci:password@{host}:5432/{database}"
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("MENTORIA_M2B_ALLOW_SCHEMA_TEST", "true")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("MENTORIA_M2B_TEST_DATABASE_URL", url)


def test_only_disposable_db_allowed(monkeypatch):
    _configure(monkeypatch)
    gate.preflight()


@pytest.mark.parametrize("bad_db,bad_host", [
    ("production", "127.0.0.1"), ("mentoria_ci_m2b_test", "company.db.tld"),
])
def test_reject_non_disposable_targets(monkeypatch, bad_db, bad_host):
    _configure(monkeypatch, database=bad_db, host=bad_host)
    with pytest.raises(RuntimeError, match="STOP"):
        gate.preflight()


def test_reject_missing_explicit_flag(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("MENTORIA_M2B_ALLOW_SCHEMA_TEST")
    with pytest.raises(RuntimeError, match="STOP"):
        gate.preflight()


def test_junit_gate_rejects_skipped_tests(monkeypatch, tmp_path):
    _configure(monkeypatch)
    xml = tmp_path/"j.xml"
    ET.ElementTree(ET.Element("testsuite", tests="7", skipped="1", failures="0", errors="0")).write(xml)
    with pytest.raises(RuntimeError, match="STOP"):
        gate.junit(str(xml))


def test_junit_gate_accepts_seven_executed_tests(monkeypatch, tmp_path):
    _configure(monkeypatch)
    xml = tmp_path/"j.xml"
    ET.ElementTree(ET.Element("testsuite", tests="7", skipped="0", failures="0", errors="0")).write(xml)
    gate.junit(str(xml))
