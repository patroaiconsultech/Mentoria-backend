"""Static-only guard tests for EFATA 777 proposed schema recovery.

No Alembic import, runtime ORM import, connections, or DDL.
Passing this test is NOT PostgreSQL qualification.
"""
from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"
FILES = (
    "001_v2_foundation.py",
    "014_thread_agent_grants.py",
    "015_thread_collaboration_capabilities.py",
    "016_thread_participant_access_expiry.py",
)
EXPECTED = {
    "001_v2_foundation": None,
    "014_thread_agent_grants": "013_agent_studio_control_plane",
    "015_thread_collaboration_capabilities": "014_thread_agent_grants",
    "016_thread_participant_access_expiry": "015_thread_collaboration_capabilities",
}


def _tree(name: str) -> ast.Module:
    return ast.parse((VERSIONS / name).read_text(encoding="utf-8"), filename=name)


def _assignments(tree: ast.Module) -> dict[str, object]:
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("revision", "down_revision"):
                    found[target.id] = ast.literal_eval(node.value)
    return found


def _call_lines(tree: ast.AST, method: str) -> list[int]:
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute) and node.func.attr == method
            or isinstance(node.func, ast.Name) and node.func.id == method
        )
    )


class SchemaRecoveryProposalStaticTests(unittest.TestCase):
    def test_all_four_files_exist(self):
        for filename in FILES:
            with self.subTest(filename=filename):
                self.assertTrue((VERSIONS / filename).is_file())

    def test_revision_lineage(self):
        for filename in FILES:
            with self.subTest(filename=filename):
                info = _assignments(_tree(filename))
                self.assertIn(info["revision"], EXPECTED)
                self.assertEqual(EXPECTED[info["revision"]], info["down_revision"])

    def test_version_table_widening_precedes_create_all(self):
        tree = _tree(FILES[0])
        widen = _call_lines(tree, "alter_column")
        create = _call_lines(tree, "create_all")
        self.assertEqual(len(widen), 1)
        self.assertEqual(len(create), 1)
        self.assertLess(widen[0], create[0])
        src = (VERSIONS / FILES[0]).read_text(encoding="utf-8")
        for required in (
            '"alembic_version"',
            '"version_num"',
            "sa.String(32)",
            "sa.String(64)",
            'bind.dialect.name != "postgresql"',
            "STOP_SCHEMA_REHEARSAL_REQUIRES_POSTGRESQL",
        ):
            with self.subTest(required=required):
                self.assertIn(required, src)

    def test_preflight_before_column_ddl(self):
        for filename in FILES[1:]:
            with self.subTest(filename=filename):
                tree = _tree(filename)
                preflights = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "_preflight_columns"
                ]
                self.assertEqual(len(preflights), 1)
                src = (VERSIONS / filename).read_text(encoding="utf-8")
                for sentinel in (
                    "STOP_REQUIRED_TABLE_MISSING",
                    "STOP_COLUMN_CONTRACT_MISMATCH",
                    'current.get("nullable") is not True',
                    'current.get("default") is not None',
                ):
                    self.assertIn(sentinel, src)
                upgrades = [
                    node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
                ]
                self.assertEqual(len(upgrades), 1)
                up = upgrades[0]
                preflight_lines = _call_lines(up, "_preflight_columns")
                add_lines = _call_lines(up, "add_column")
                self.assertEqual(len(preflight_lines), 1)
                self.assertEqual(len(add_lines), 1)
                self.assertLess(preflight_lines[0], add_lines[0])

    def test_required_scope_names_014(self):
        txt = (VERSIONS / FILES[1]).read_text(encoding="utf-8")
        self.assertIn("allowed_agent_ids", txt)
        self.assertIn("thread_participants", txt)
        self.assertIn("thread_invitations", txt)
        self.assertIn("sa.JSON()", txt)

    def test_required_capabilities_015(self):
        txt = (VERSIONS / FILES[2]).read_text(encoding="utf-8")
        for name in ("can_read_messages", "can_write_messages",
                     "thread_participants", "thread_invitations", "sa.Boolean()"):
            self.assertIn(name, txt)

    def test_required_expiry_016(self):
        txt = (VERSIONS / FILES[3]).read_text(encoding="utf-8")
        for name in (
            "access_duration_hours", "access_expires_at",
            "ck_thread_invitation_access_duration",
            "STOP_CONSTRAINT_CONTRACT_MISMATCH",
            "sa.DateTime(timezone=True)",
        ):
            self.assertIn(name, txt)

    def test_expiry_checks_before_any_upgrade_ddl(self):
        tree = _tree(FILES[3])
        upgrade = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef) and node.name == "upgrade")
        check_lines = _call_lines(upgrade, "_duration_constraint_missing")
        op_lines = _call_lines(upgrade, "add_column") + _call_lines(
            upgrade, "create_check_constraint"
        )
        self.assertEqual(len(check_lines), 1)
        self.assertTrue(op_lines)
        self.assertLess(check_lines[0], min(op_lines))

    def test_no_environment_or_auth_bypass_in_candidates(self):
        for filename in FILES:
            with self.subTest(filename=filename):
                txt = (VERSIONS / filename).read_text(encoding="utf-8")
                for forbidden in ("DATABASE_URL=", "god_mode", "bypass_auth", "alembic stamp"):
                    self.assertNotIn(forbidden, txt)

    def test_long_revision_identifiers(self):
        self.assertGreater(len("015_thread_collaboration_capabilities"), 32)
        self.assertGreater(len("016_thread_participant_access_expiry"), 32)


if __name__ == "__main__":
    unittest.main()
