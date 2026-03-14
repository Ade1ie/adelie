"""
adelie/utils/dep_sync.py

Dependency synchronization — detects imports in staged source files
and checks if they are declared in package.json / requirements.txt.
Reports missing dependencies for next-cycle awareness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


# Known built-in / Node.js standard modules (do not flag these)
_NODE_BUILTINS = {
    "fs", "path", "os", "http", "https", "url", "util", "stream",
    "crypto", "events", "buffer", "net", "child_process", "cluster",
    "assert", "readline", "zlib", "querystring", "string_decoder",
    "tty", "dgram", "dns", "domain", "punycode", "v8", "vm",
    "worker_threads", "perf_hooks", "async_hooks", "inspector",
    "react", "react-dom",  # These are always present in React projects
}

# Patterns that are relative imports (not packages)
_RELATIVE_PATTERNS = {"./", "../", "@/", "~/"}


def _extract_js_imports(content: str) -> set[str]:
    """Extract package names from JS/TS import statements."""
    packages: set[str] = set()

    # import ... from 'package' or import ... from "package"
    for match in re.finditer(r'''(?:import|from)\s+['"]([^'"]+)['"]''', content):
        mod = match.group(1)
        if any(mod.startswith(p) for p in _RELATIVE_PATTERNS):
            continue
        # Extract package name: @scope/pkg or pkg
        if mod.startswith("@"):
            parts = mod.split("/")
            if len(parts) >= 2:
                packages.add(f"{parts[0]}/{parts[1]}")
        else:
            packages.add(mod.split("/")[0])

    # require('package')
    for match in re.finditer(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''', content):
        mod = match.group(1)
        if any(mod.startswith(p) for p in _RELATIVE_PATTERNS):
            continue
        if mod.startswith("@"):
            parts = mod.split("/")
            if len(parts) >= 2:
                packages.add(f"{parts[0]}/{parts[1]}")
        else:
            packages.add(mod.split("/")[0])

    return packages - _NODE_BUILTINS


def _extract_py_imports(content: str) -> set[str]:
    """Extract third-party package names from Python import statements."""
    packages: set[str] = set()
    stdlib = {
        "os", "sys", "re", "json", "math", "datetime", "pathlib",
        "typing", "collections", "itertools", "functools", "io",
        "subprocess", "shutil", "time", "logging", "unittest",
        "dataclasses", "enum", "abc", "copy", "hashlib", "base64",
        "argparse", "contextlib", "threading", "multiprocessing",
        "socket", "http", "urllib", "email", "html", "xml",
        "sqlite3", "csv", "configparser", "textwrap", "string",
        "struct", "array", "queue", "heapq", "bisect",
        "__future__", "warnings", "traceback", "inspect",
        "signal", "glob", "tempfile", "pickle", "shelve",
        "pprint", "dis", "ast", "token", "tokenize",
    }

    for match in re.finditer(r'^(?:import|from)\s+(\S+)', content, re.MULTILINE):
        mod = match.group(1).split(".")[0]
        if mod not in stdlib and not mod.startswith("_"):
            packages.add(mod)

    return packages


def scan_missing_deps(
    staged_files: list[dict],
    staging_root: Path,
    project_root: Path,
) -> list[str]:
    """
    Parse imports from staged files, compare with package.json/requirements.txt.
    Returns list of missing package names.
    """
    js_exts = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
    py_exts = {".py"}

    all_js_imports: set[str] = set()
    all_py_imports: set[str] = set()

    for finfo in staged_files:
        filepath = finfo.get("filepath", "")
        full_path = staging_root / filepath
        if not full_path.exists():
            continue

        ext = full_path.suffix.lower()
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            continue

        if ext in js_exts:
            all_js_imports |= _extract_js_imports(content)
        elif ext in py_exts:
            all_py_imports |= _extract_py_imports(content)

    missing: list[str] = []

    # Check JS imports against package.json
    if all_js_imports:
        pkg_path = project_root / "package.json"
        declared: set[str] = set()
        if pkg_path.exists():
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                declared |= set(pkg.get("dependencies", {}).keys())
                declared |= set(pkg.get("devDependencies", {}).keys())
                declared |= set(pkg.get("peerDependencies", {}).keys())
            except Exception:
                pass

        js_missing = all_js_imports - declared - _NODE_BUILTINS
        missing.extend(sorted(js_missing))

    # Check Python imports against requirements.txt
    if all_py_imports:
        req_path = project_root / "requirements.txt"
        declared_py: set[str] = set()
        if req_path.exists():
            try:
                for line in req_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Extract package name (before ==, >=, etc.)
                        pkg_name = re.split(r'[>=<!\[]', line)[0].strip().lower()
                        declared_py.add(pkg_name)
            except Exception:
                pass

        py_missing = {p for p in all_py_imports if p.lower() not in declared_py}
        missing.extend(sorted(py_missing))

    return missing


def sync_package_json(missing: list[str], project_root: Path) -> int:
    """
    Add missing JS packages to package.json dependencies.
    Uses '*' as version placeholder — Runner AI will npm install later.
    Returns count of added packages.
    """
    pkg_path = project_root / "package.json"
    if not pkg_path.exists() or not missing:
        return 0

    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    deps = pkg.setdefault("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})
    added = 0

    for name in missing:
        if name not in deps and name not in dev_deps:
            # Heuristic: testing/dev tools go to devDependencies
            if any(kw in name.lower() for kw in ["test", "jest", "vitest", "eslint", "prettier", "lint"]):
                dev_deps = pkg.setdefault("devDependencies", {})
                dev_deps[name] = "*"
            else:
                deps[name] = "*"
            added += 1

    if added:
        pkg_path.write_text(
            json.dumps(pkg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return added
