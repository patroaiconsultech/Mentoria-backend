#!/usr/bin/env python3
"""Import the EFATÀ 777 mentoria source candidate WITHOUT git commit, push or deploy.

Rejects symlinks, unknown preimages, dirty target and main branch.
Default is --check. --apply requires a pinned HEAD SHA on a feature branch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class GateError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise GateError(f"git {' '.join(args)} falhou: {result.stderr.strip()[:160]}")
    return result.stdout.strip()


def assert_safe(path: Path, root: Path) -> None:
    rel = path.relative_to(root)
    if not rel.parts or any(x in ("", ".", "..", ".git") for x in rel.parts):
        raise GateError("Caminho inseguro")
    cursor = root
    for segment in rel.parts:
        cursor /= segment
        if cursor.is_symlink():
            raise GateError(f"Symlink recusado: {rel}")


def run(repo_name: str, target: Path, mode: str, expected_head: str | None) -> int:
    package_root = Path(__file__).resolve().parents[1]
    data = json.loads((package_root / "manifest.json").read_text(encoding="utf-8"))
    payload_root = package_root / "payload" / repo_name
    target = target.resolve(strict=True)
    if not target.is_dir() or not (target / ".git").exists():
        raise GateError("Target precisa ser um clone Git local (worktree raiz)")
    if mode == "apply":
        if not expected_head or not re.fullmatch(r"[0-9a-f]{40}", expected_head):
            raise GateError("--apply exige --expected-head SHA completo (40 hex)")
        actual = git(target, "rev-parse", "HEAD")
        branch = git(target, "branch", "--show-current")
        if actual != expected_head:
            raise GateError("HEAD mudou: abortado")
        if not branch.startswith("feature/mentoria"):
            raise GateError("Use uma branch feature/mentoria*; não edite main diretamente")
        if git(target, "status", "--porcelain"):
            raise GateError("Worktree deve estar limpo")
    entries = data["repos"][repo_name]["files"]
    pending: list[tuple[Path, Path]] = []
    for rel_str, spec in entries.items():
        rel = Path(rel_str)
        if rel.is_absolute() or ".." in rel.parts:
            raise GateError(f"Caminho inseguro no manifesto: {rel_str}")
        source = payload_root / rel
        dest = target / rel
        assert_safe(source, payload_root)
        assert_safe(dest, target)
        if not source.is_file() or digest(source) != spec["new_sha256"]:
            raise GateError(f"Payload divergente: {rel}")
        expected_old = spec.get("old_sha256")
        actual_old = digest(dest) if dest.exists() and dest.is_file() else None
        if actual_old == spec["new_sha256"]:
            continue  # Previously imported unchanged: safe idempotence.
        if actual_old != expected_old:
            raise GateError(f"Conflito: {rel}: preimage mudou ou arquivo novo já existe")
        pending.append((source, dest))
    print(json.dumps({
        "status": "READY_FOR_LOCAL_APPLY" if pending else "ALREADY_IDENTICAL",
        "repo": repo_name,
        "mode": mode,
        "pending": len(pending),
        "total": len(entries),
        "head": git(target, "rev-parse", "HEAD"),
    }, ensure_ascii=False))
    if mode == "apply":
        # All preimages validated BEFORE first write. No checkout/commit/push/merge/deploy.
        for source, dest in pending:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive temp name avoids partial writes; preimage already checked.
            temporary = dest.with_name(dest.name + ".mentoria-pending")
            if temporary.exists() or temporary.is_symlink():
                raise GateError(f"Arquivo temporário pré-existente: {temporary}")
            try:
                with temporary.open("xb") as handle:
                    handle.write(source.read_bytes())
                os.replace(temporary, dest)
            finally:
                temporary.unlink(missing_ok=True)
        print(f"APPLIED_LOCAL_ONLY={len(pending)}; faça diff/testes antes de git add")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, choices=("backend", "frontend"))
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--mode", default="check", choices=("check", "apply"))
    parser.add_argument("--expected-head", help="SHA completo do HEAD local; obrigatório em --apply")
    args = parser.parse_args()
    try:
        return run(args.repo, args.target, args.mode, args.expected_head)
    except (GateError, FileNotFoundError, ValueError, KeyError) as exc:
        print(f"STOP_NO_WRITE={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
