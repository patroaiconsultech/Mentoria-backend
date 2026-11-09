"""Guard PostgreSQL tests and prove JUnit has no skipped gate tests.

Never uses production DB. No DDL here; migration execution belongs to
the isolated GitHub Actions job after `preflight` passes.
"""
from __future__ import annotations
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from sqlalchemy.engine.url import make_url


def preflight() -> None:
    if os.getenv("CI") != "true" or os.getenv("MENTORIA_M2B_ALLOW_SCHEMA_TEST") != "true":
        raise RuntimeError("STOP: CI and explicit schema test approval required")
    a = make_url(os.environ["DATABASE_URL"])
    b = make_url(os.environ["MENTORIA_M2B_TEST_DATABASE_URL"])
    if a != b:
        raise RuntimeError("STOP: database targets must match")
    if a.get_backend_name() != "postgresql" or a.host not in ("127.0.0.1", "localhost"):
        raise RuntimeError("STOP: only disposable local PostgreSQL service allowed")
    if a.database != "mentoria_ci_m2b_test":
        raise RuntimeError("STOP: only explicit disposable test database allowed")
    if a.username != "mentoria_ci":
        raise RuntimeError("STOP: unexpected DB role")
    print("MENTORIA_PG_PREFLIGHT=PASS (isolated test target)")


def head() -> None:
    """Require the candidate revision, without claiming it is runtime."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, text
    preflight()
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    expected = "019_mentoria_webhook_inbox"
    if script.get_current_head() != expected:
        raise RuntimeError("STOP: candidate Alembic HEAD differs")
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        actual = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    if actual != expected:
        raise RuntimeError("STOP: disposable DB migration mismatch")
    print("MENTORIA_ALEMBIC_HEAD=PASS (disposable PostgreSQL only)")


def junit(filename: str) -> None:
    preflight()
    root = ET.parse(Path(filename)).getroot()
    # Either <testsuite> or <testsuites>; aggregate on leaf suites.
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(node.get("tests", "0")) for node in suites)
    failures = sum(int(node.get("failures", "0")) for node in suites)
    errors = sum(int(node.get("errors", "0")) for node in suites)
    skipped = sum(int(node.get("skipped", "0")) for node in suites)
    if tests < 7 or skipped or failures or errors:
        raise RuntimeError(
            f"STOP: PG gate tests={tests} failures={failures} errors={errors} skipped={skipped}"
        )
    print(f"MENTORIA_PG_TESTS=PASS ({tests} tests, zero skips)")


if __name__ == "__main__":
    operation = sys.argv[1] if len(sys.argv) > 1 else ""
    if operation == "preflight" and len(sys.argv) == 2:
        preflight()
    elif operation == "head" and len(sys.argv) == 2:
        head()
    elif operation == "junit" and len(sys.argv) == 3:
        junit(sys.argv[2])
    else:
        raise SystemExit("usage: mentoria_pg_gate.py {preflight|head|junit <xml>}")
