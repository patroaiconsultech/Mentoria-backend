#!/usr/bin/env python3
"""EFATA 777 — evidence-only fresh PostgreSQL Alembic 001..016 rehearsal.

Run ONLY by the deliberately dispatched branch-specific GitHub Actions job.
No Railway variables, no operational database, no DROP/RESET/STAMP/DOWNGRADE.
Alembic itself performs its versioned DDL on an ephemeral CI service.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import sqlalchemy as sa
from sqlalchemy.engine import make_url

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_HASHES = {'migrations/versions/001_v2_foundation.py': '9be555b08ac221500255852eca292b5b0f14b6602aa3c47c9c0279afb242940c',
 'migrations/versions/002_hyper_cocreator_onboarding.py': '209ffc9ca54586f80d38b7c5c71aa18fc78095fef84455115ee0585a24103ec5',
 'migrations/versions/003_native_auth.py': 'a663401cd3b094b712d97b507fb785b53e47e9bd322af7a418d3b84ff492761b',
 'migrations/versions/004_rc1_auth_d_hardening.py': '16475bc457407ae4757d41b829d634e966113a0ab97156e15efbb409d41b15fc',
 'migrations/versions/005_knowledge_plane_v1.py': 'eb47c08aceefdb1713a01489e0f380ba2b42ead79addb250f791ecddde0f2533',
 'migrations/versions/006_knowledge_plane_hardening.py': '85d857d9c88ae3761ad7a743a76718351b515edfc4ffcfe1ffb5972e6a7292f5',
 'migrations/versions/007_large_document_b1_b2.py': '392474b5ae425e0a4f176df2aceece8d0f213daf31d316aefe9729387976d3e6',
 'migrations/versions/008_admin_voice_catalog.py': '0252a9b0f70602fa047ede8ddd7817e6b016405013de38147ea6bdc8345093cc',
 'migrations/versions/009_audit_evidence_ledger.py': '5f1c608ee608862c10e266d2709b1c012bc5109f18d247068c091d71e4820441',
 'migrations/versions/010_billing_core.py': '6435cf516c15daaf182aeaa291c53aa9bd35d50db12195a5bb7a8cbf8e6a6db8',
 'migrations/versions/011_billing_wallet.py': '8625346331ca4d4a1eb11dd27b57f86325571a17aec6083bf00ce8aa3553e72b',
 'migrations/versions/012_platform_user_invitations.py': 'bcd0fd7b1b854efcdc4530c995c7423cb6aa399a2571a9345745f9aadc899bd8',
 'migrations/versions/013_agent_studio_control_plane.py': 'f8ed79326bb7334cff667c10efaeac159ca8edf9877f4495d56a875ea7b2a898',
 'migrations/versions/014_thread_agent_grants.py': '59a5c99c9ca5cb97be90bf9ebb250018b0ad8ddb47faf8b02d94b0aa7b536140',
 'migrations/versions/015_thread_collaboration_capabilities.py': 'b4c0da3b857c8d2b3434f46f5bd5d06dcfab7e0e1c0a96ba6e8a17914cfb7ab8',
 'migrations/versions/016_thread_participant_access_expiry.py': 'a159c019df6ba652c8da01fa3387d5b5d473a1eff2c24859c85c2b25ae9894bf',
 'migrations/env.py': '35cda4e57a85806cd8636dd3b7048a537a21e0c9d05c011c4d7f3f67018f5491',
 'src/orkio_v2/models.py': 'd0e31d86723d7b7baea15aff6958b6595f3fafc4b25e908e758b1d4b752a2529'}
REVISIONS = ['001_v2_foundation.py',
 '002_hyper_cocreator_onboarding.py',
 '003_native_auth.py',
 '004_rc1_auth_d_hardening.py',
 '005_knowledge_plane_v1.py',
 '006_knowledge_plane_hardening.py',
 '007_large_document_b1_b2.py',
 '008_admin_voice_catalog.py',
 '009_audit_evidence_ledger.py',
 '010_billing_core.py',
 '011_billing_wallet.py',
 '012_platform_user_invitations.py',
 '013_agent_studio_control_plane.py',
 '014_thread_agent_grants.py',
 '015_thread_collaboration_capabilities.py',
 '016_thread_participant_access_expiry.py']
REVISION_IDS = {'001_v2_foundation.py': '001_v2_foundation',
 '002_hyper_cocreator_onboarding.py': '002_hyper_cocreator',
 '003_native_auth.py': '003_native_auth',
 '004_rc1_auth_d_hardening.py': '004_rc1_auth_d',
 '005_knowledge_plane_v1.py': '005_knowledge_plane_v1',
 '006_knowledge_plane_hardening.py': '006_knowledge_plane_hardening',
 '007_large_document_b1_b2.py': '007_large_document_b1_b2',
 '008_admin_voice_catalog.py': '008_admin_voice_catalog',
 '009_audit_evidence_ledger.py': '009_audit_evidence_ledger',
 '010_billing_core.py': '010_billing_core',
 '011_billing_wallet.py': '011_billing_wallet',
 '012_platform_user_invitations.py': '012_platform_user_invitations',
 '013_agent_studio_control_plane.py': '013_agent_studio_control_plane',
 '014_thread_agent_grants.py': '014_thread_agent_grants',
 '015_thread_collaboration_capabilities.py': '015_thread_collaboration_capabilities',
 '016_thread_participant_access_expiry.py': '016_thread_participant_access_expiry'}
STOP = "STOP_AND_PRESERVE"


def emit(stage: str, status: str, **details: object) -> None:
    print(json.dumps({"stage": stage, "status": status, **details},
                     ensure_ascii=False, sort_keys=True), flush=True)


def require(predicate: bool, code: str) -> None:
    if not predicate:
        raise RuntimeError(f"{STOP}:{code}")


def preflight() -> sa.Engine:
    require(os.getenv("GITHUB_ACTIONS") == "true", "NOT_GITHUB_ACTIONS")
    require(os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch",
            "NOT_EXPLICIT_MANUAL_DISPATCH")
    require(os.getenv("GITHUB_REF") == "refs/heads/fix/schema-recovery-staging",
            "WRONG_BRANCH")
    require(os.getenv("GITHUB_REPOSITORY") ==
            "patroaiconsultech/efata-777-backend-staging-web01",
            "WRONG_REPOSITORY")
    require(os.getenv("CI", "").lower() == "true", "NOT_CI")
    require(not (ROOT / ".env").exists(), "LOCAL_DOTENV_FILE_FORBIDDEN")
    require(not any(k.startswith(("RAILWAY_", "PGPASSWORD")) for k in os.environ),
            "OPERATIONAL_ENVIRONMENT_VARIABLE_PRESENT")
    raw = os.getenv("DATABASE_URL", "").strip()
    require(bool(raw), "DATABASE_URL_MISSING")
    url = make_url(raw)
    require(url.drivername == "postgresql+psycopg", "WRONG_DATABASE_DRIVER")
    require(url.host == "127.0.0.1" and url.port == 5432,
            "DATABASE_NOT_LOCALHOST")
    require(url.database == "patroai_ci" and url.username == "patroai_ci",
            "DATABASE_NOT_EPHEMERAL_CI")
    require(bool(url.password), "CI_DATABASE_PASSWORD_MISSING")
    for name, digest in SOURCE_HASHES.items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT.resolve()) and path.is_file(),
                "SOURCE_MISSING:" + name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == digest, "SOURCE_HASH_MISMATCH:" + name)
    previous = None
    for name in REVISIONS:
        path = ROOT / "migrations" / "versions" / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assignments = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ("revision", "down_revision"):
                        assignments[target.id] = ast.literal_eval(node.value)
        require(assignments.get("revision") == REVISION_IDS[name],
                "REVISION_ID_MISMATCH:" + name)
        require(assignments.get("down_revision") == previous,
                "REVISION_LINEAGE_MISMATCH:" + name)
        previous = assignments["revision"]
    # env.py imports get_settings().database_url independently. Ensure
    # it resolves to the same isolated DSN, not a different target.
    from orkio_v2.config import get_settings
    from orkio_v2.database import normalize_database_url
    effective = normalize_database_url(get_settings().database_url)
    require(effective == raw, "ALEMBIC_EFFECTIVE_TARGET_MISMATCH")
    engine = sa.create_engine(raw, pool_pre_ping=True)
    with engine.connect() as connection:
        pg_version = connection.execute(
            sa.text("SELECT current_setting('server_version_num')::integer")
        ).scalar_one()
        require(160000 <= pg_version < 170000, "POSTGRESQL_MAJOR_NOT_16")
        name, username = connection.execute(
            sa.text("SELECT current_database(), current_user")
        ).one()
        count = connection.execute(sa.text("""
            SELECT count(*)
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','S')
        """)).scalar_one()
        require(name == "patroai_ci" and username == "patroai_ci",
                "CONNECTED_TO_UNEXPECTED_DATABASE")
        require(count == 0, "DATABASE_NOT_EMPTY")
    emit("preflight", "PASS", database="patroai_ci", host="127.0.0.1",
         fresh_database=True, postgresql_major=16, source_hashes=len(SOURCE_HASHES))
    return engine


def state(engine: sa.Engine, expected: str) -> None:
    with engine.connect() as connection:
        result = connection.execute(
            sa.text("SELECT version_num FROM public.alembic_version")
        ).scalars().all()
        require(result == [expected], "ALEMBIC_VERSION_MISMATCH:" + expected)
        width = connection.execute(sa.text("""
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='alembic_version'
              AND column_name='version_num'
        """)).scalar_one()
        require(width == 64, "ALEMBIC_VERSION_WIDTH_NOT_64")
        tables = {row[0] for row in connection.execute(sa.text("""
            SELECT tablename FROM pg_catalog.pg_tables
            WHERE schemaname='public'
        """))}
        require("native_credentials" in tables, "AUTH_TABLE_MISSING")
        require({"users", "tenants", "memberships"} <= tables,
                "IDENTITY_TABLES_MISSING")
        emit("revision", "PASS", revision=expected, public_tables=len(tables))


def normalized_email_index(engine: sa.Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT i.indisunique, i.indisvalid, i.indisready,
                   pg_get_indexdef(i.indexrelid),
                   pg_get_expr(i.indpred, i.indrelid),
                   pg_get_expr(i.indexprs, i.indrelid)
            FROM pg_catalog.pg_index i
            JOIN pg_catalog.pg_class ix ON ix.oid = i.indexrelid
            JOIN pg_catalog.pg_namespace ns ON ns.oid=ix.relnamespace
            JOIN pg_catalog.pg_class tbl ON tbl.oid=i.indrelid
            WHERE ns.nspname='public' AND tbl.relname='users'
              AND ix.relname='uq_users_email_normalized'
        """)).all()
    require(len(rows) == 1, "EMAIL_INDEX_MISSING_OR_DUPLICATED")
    unique, valid, ready, definition, predicate, expression = rows[0]
    require(bool(unique) and bool(valid) and bool(ready),
            "EMAIL_INDEX_NOT_VALID_UNIQUE_READY")
    require(predicate is None, "EMAIL_INDEX_UNEXPECTED_PREDICATE")
    normalized = re.sub(r"\s+", "", str(expression or "").lower())
    require("lower(" in normalized and ("trim(" in normalized or "btrim(" in normalized) and "email" in normalized,
            "EMAIL_INDEX_EXPRESSION_MISMATCH")
    emit("index_012", "PASS", unique=True, valid=True, ready=True,
         expression=str(expression))


def columns_014_016(engine: sa.Engine, revision: int) -> None:
    specs = []
    if revision >= 14:
        specs += [(t, "allowed_agent_ids", "json")
                  for t in ("thread_participants", "thread_invitations")]
    if revision >= 15:
        specs += [(t, col, "boolean")
                  for t in ("thread_participants", "thread_invitations")
                  for col in ("can_read_messages", "can_write_messages")]
    if revision >= 16:
        specs += [
            ("thread_invitations", "access_duration_hours", "integer"),
            ("thread_participants", "access_expires_at", "timestamp with time zone"),
        ]
    with engine.connect() as conn:
        for tbl, col, expected_type in specs:
            result = conn.execute(sa.text("""
                SELECT data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:table_name
                  AND column_name=:column_name
            """), {"table_name": tbl, "column_name": col}).all()
            require(len(result) == 1, "COLUMN_MISSING:" + tbl + "." + col)
            typ, nullable, default = result[0]
            require(typ == expected_type and nullable == "YES" and default is None,
                    "COLUMN_CONTRACT_MISMATCH:" + tbl + "." + col)
        if revision >= 16:
            checks = conn.execute(sa.text("""
                SELECT pg_get_constraintdef(c.oid)
                FROM pg_catalog.pg_constraint c
                JOIN pg_catalog.pg_class tbl ON tbl.oid=c.conrelid
                JOIN pg_catalog.pg_namespace ns ON ns.oid=tbl.relnamespace
                WHERE ns.nspname='public'
                  AND tbl.relname='thread_invitations'
                  AND c.conname='ck_thread_invitation_access_duration'
                  AND c.contype='c'
            """)).scalars().all()
            require(len(checks) == 1, "DURATION_CHECK_MISSING")
            check = checks[0].lower()
            require("access_duration_hours" in check
                    and "1" in check and "8760" in check,
                    "DURATION_CHECK_UNEXPECTED")
    emit("columns_014_016", "PASS", revision=revision, columns=len(specs))


def final_shape(engine: sa.Engine) -> None:
    from orkio_v2.database import Base
    from orkio_v2 import models  # noqa: F401 -- register mapped tables

    expected_tables = set(Base.metadata.tables)
    actual_tables = set(sa.inspect(engine).get_table_names())
    missing = expected_tables - actual_tables
    require(not missing, "ORM_TABLES_MISSING:" + ",".join(sorted(missing)))
    emit("final", "PASS", orm_tables=len(expected_tables),
         database_tables=len(actual_tables), alembic_head=REVISION_IDS[REVISIONS[-1]])


def migrate(revision: str) -> None:
    command = [sys.executable, "-m", "alembic", "upgrade", revision]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            timeout=180, check=False)
    if result.returncode:
        # Never print raw SQLAlchemy/Alembic output: could include connection details.
        details = re.findall(
            r"(?:psycopg\.errors\.[A-Za-z_]+|sqlalchemy\.exc\.[A-Za-z_]+"
            r"|ERROR: [^\n]{0,120})", result.stderr + "\n" + result.stdout
        )
        reason = ",".join(details[-2:])[:240]
        raise RuntimeError(
            f"{STOP}:ALEMBIC_UPGRADE_FAILED:{revision}:exit={result.returncode}:"
            f"{reason or 'NO_SAFE_DIAGNOSTIC'}"
        )


def preserve_failure_catalog(engine: sa.Engine) -> None:
    """Read-only, bounded failure evidence from the ephemeral CI database."""
    try:
        inspector = sa.inspect(engine)
        present = set(inspector.get_table_names(schema="public"))
        revision = None
        with engine.connect() as conn:
            if "alembic_version" in present:
                versions = conn.execute(sa.text(
                    "SELECT version_num FROM public.alembic_version LIMIT 2"
                )).scalars().all()
                revision = versions[0] if len(versions) == 1 else "INVALID_VERSION_ROWS"
            index_rows = conn.execute(sa.text("""
                SELECT i.indisvalid, i.indisready
                FROM pg_catalog.pg_index i
                JOIN pg_catalog.pg_class ix ON ix.oid = i.indexrelid
                JOIN pg_catalog.pg_namespace n ON n.oid=ix.relnamespace
                WHERE n.nspname='public'
                  AND ix.relname='uq_users_email_normalized'
            """)).all()
        emit("failure_catalog", "RECORDED", alembic_revision=revision,
             table_count=len(present),
             email_index=[{"valid": bool(row[0]), "ready": bool(row[1])}
                          for row in index_rows[:2]])
    except Exception as exc:
        emit("failure_catalog", "NOT_PROVEN", error_type=type(exc).__name__)


def main() -> int:
    engine = None
    try:
        engine = preflight()
        for n, filename in enumerate(REVISIONS, start=1):
            rev = REVISION_IDS[filename]
            emit("before_revision", "START", revision=rev)
            migrate(rev)
            state(engine, rev)
            if n >= 12:
                normalized_email_index(engine)
            if n >= 14:
                columns_014_016(engine, n)
        final_shape(engine)
        emit("full_chain", "PASS", total_revisions=len(REVISIONS))
        return 0
    except Exception as exc:
        # Failure on an ephemeral CI DB only: keep its state for job lifetime.
        reason = str(exc)[:300] if isinstance(exc, RuntimeError) and str(exc).startswith(STOP) else f"UNEXPECTED_EXCEPTION:{type(exc).__name__}"
        emit("full_chain", "STOP", reason=reason)
        if engine is not None:
            preserve_failure_catalog(engine)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
