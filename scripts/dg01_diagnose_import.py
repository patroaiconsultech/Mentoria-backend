#!/usr/bin/env python3
"""DG-01: build-only import smoke with sanitized, stdout-first diagnostics.

Do not log environment values or exception messages: some validation exceptions
may embed credentials. Preserve failure: nonzero exit means build must fail.
"""
from __future__ import annotations

import importlib
import re
import sys
import traceback
from pathlib import Path


def _safe_module_name(error: BaseException) -> str:
    name = getattr(error, "name", None)
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
        return "<indisponivel>"
    return name


def _safe_filename(filename: str) -> str:
    path = filename.replace("\\", "/")
    if path.startswith("/app/"):
        return path[5:]
    return Path(path).name


def main() -> int:
    print("DG01_APP_IMPORT_BEGIN", flush=True)
    try:
        importlib.import_module("orkio_v2.main")
    except BaseException as exc:
        print(f"DG01_APP_IMPORT_FAILED_TYPE={type(exc).__name__}", flush=True)
        print(f"DG01_APP_IMPORT_FAILED_MODULE={_safe_module_name(exc)}", flush=True)
        for frame in traceback.extract_tb(exc.__traceback__)[-20:]:
            print(
                f"DG01_APP_IMPORT_FRAME={_safe_filename(frame.filename)}"
                f":{frame.lineno}:{frame.name}",
                flush=True,
            )
        return 1
    print("DG01_APP_IMPORT_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
