#!/usr/bin/env python3
"""Somente leitura: compara árvore de código e imports de main.py; não importa aplicação."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main_dependencies(root: Path) -> list[str]:
    src = root / "src" / "orkio_v2"
    entry = src / "main.py"
    if not entry.is_file():
        raise ValueError(f"main.py ausente: {entry}")
    parsed = ast.parse(entry.read_text(encoding="utf-8"), filename=str(entry))
    missing: set[str] = set()
    for node in ast.walk(parsed):
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        # Importação relativa ao pacote orkio_v2 no módulo main.py.
        module = (node.module or "").replace(".", "/")
        if not module:
            continue
        file_path = src / (module + ".py")
        pkg_path = src / module / "__init__.py"
        # Pacote namespace só é admitido quando há arquivos reais abaixo.
        namespace_dir = src / module
        if not (file_path.is_file() or pkg_path.is_file() or
                (namespace_dir.is_dir() and any(namespace_dir.rglob("*.py")))):
            missing.add(module)
    return sorted(missing)

def audit(root: Path, expected: dict[str, str]) -> dict[str, object]:
    missing: list[str] = []
    divergent: list[str] = []
    matching = 0
    for rel, sha in expected.items():
        path = root / rel
        if not path.is_file():
            missing.append(rel)
        elif sha256_file(path) != sha:
            divergent.append(rel)
        else:
            matching += 1
    return {"matching": matching, "missing": missing, "divergent": divergent,
            "main_imports_missing": main_dependencies(root)}

def cli() -> int:
    parser = argparse.ArgumentParser(
        description="Auditoria LOCAL e SOMENTE LEITURA: nenhum upload, copy ou modificação."
    )
    parser.add_argument("backend_root", type=Path, help="raiz do clone backend com src/ e Dockerfile")
    parser.add_argument("--json", action="store_true", help="imprime relatório JSON")
    args = parser.parse_args()
    root = args.backend_root.resolve()
    expected = json.loads((HERE / "docs" / "BASELINE_MODULE_SHA256.json").read_text(encoding="utf-8"))
    try:
        report = audit(root, expected)
    except (OSError, ValueError, SyntaxError) as e:
        parser.error(str(e))
    if args.json:
        print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        print(f"BASELINE_MODULE_MATCHING={report['matching']}")
        print(f"BASELINE_MODULE_MISSING={len(report['missing'])}")
        print(f"BASELINE_MODULE_DIVERGENT={len(report['divergent'])}")
        print(f"MAIN_IMPORTS_MISSING={len(report['main_imports_missing'])}")
        for rel in report["missing"]:
            print("MISSING:", rel)
        for rel in report["divergent"]:
            print("DIVERGENT (não sobrescrever):", rel)
        for module in report["main_imports_missing"]:
            print("MAIN_IMPORT_MISSING:", module)
    # Divirgência pode ser atualização legítima; não falha por divergência de SHA.
    return 2 if report["missing"] or report["main_imports_missing"] else 0

if __name__ == "__main__":
    raise SystemExit(cli())
