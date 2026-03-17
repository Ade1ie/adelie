"""
adelie/utils/import_checker.py

Cross-file import consistency checker.

Validates that imported modules/files actually exist in the project,
detecting broken imports BEFORE code is promoted to production.

Checks:
  - Python: `import X` / `from X import Y` → does file exist?
  - JavaScript/TypeScript: `import ... from './path'` → does file exist?
  - Missing local imports → returns list of issues
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from rich.console import Console

console = Console()


class ImportIssue(NamedTuple):
    """A detected import consistency problem."""
    file: str        # The file containing the bad import
    line: int        # Line number (1-indexed)
    imported: str    # What's being imported
    reason: str      # Why it's a problem


# ── Python Import Checking ────────────────────────────────────────────────────

# Match: import foo.bar / from foo.bar import baz
_PY_IMPORT_RE = re.compile(
    r'^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE
)

# Standard library / builtins we should never flag
_PY_STDLIB = {
    "os", "sys", "re", "json", "math", "datetime", "pathlib", "typing",
    "collections", "functools", "itertools", "abc", "io", "copy", "time",
    "hashlib", "logging", "subprocess", "shutil", "threading", "enum",
    "dataclasses", "unittest", "pytest", "http", "urllib", "socket",
    "asyncio", "contextlib", "textwrap", "argparse", "configparser",
    "csv", "xml", "html", "email", "base64", "uuid", "random", "string",
    "struct", "traceback", "warnings", "signal", "tempfile", "glob",
    "fnmatch", "stat", "secrets", "decimal", "fractions", "operator",
    "inspect", "importlib", "pkgutil", "pprint", "calendar",
    "__future__", "concurrent", "multiprocessing", "queue",
}


def _get_python_files(root: Path) -> dict[str, Path]:
    """Map Python module names to file paths."""
    modules: dict[str, Path] = {}
    for f in root.rglob("*.py"):
        rel = f.relative_to(root)
        # Convert path to module name: src/foo/bar.py → src.foo.bar
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "")
        module_name = ".".join(parts)
        modules[module_name] = f
        # Also register just the last component for simple imports
        if len(parts) > 0:
            modules[parts[-1]] = f
    return modules


def _check_python_imports(
    file_path: Path, content: str, known_modules: dict[str, Path],
) -> list[ImportIssue]:
    """Check Python imports in a single file."""
    issues: list[ImportIssue] = []

    for line_num, line in enumerate(content.splitlines(), 1):
        line_stripped = line.strip()

        # Skip comments and empty lines
        if not line_stripped or line_stripped.startswith("#"):
            continue

        match = _PY_IMPORT_RE.match(line_stripped)
        if not match:
            continue

        module = match.group(1) or match.group(2)
        if not module:
            continue

        # Get the top-level package
        top_level = module.split(".")[0]

        # Skip stdlib and well-known third-party packages
        if top_level in _PY_STDLIB:
            continue

        # Skip common third-party packages (not local)
        if top_level in {
            "flask", "fastapi", "django", "requests", "numpy", "pandas",
            "pydantic", "sqlalchemy", "celery", "redis", "boto3", "pytest",
            "rich", "click", "typer", "httpx", "aiohttp", "starlette",
            "uvicorn", "gunicorn", "dotenv", "google", "openai",
            "adelie",  # Self-imports are okay
        }:
            continue

        # Check if the module exists locally
        if module not in known_modules and top_level not in known_modules:
            issues.append(ImportIssue(
                file=str(file_path),
                line=line_num,
                imported=module,
                reason=f"Module '{module}' not found in project",
            ))

    return issues


# ── JavaScript/TypeScript Import Checking ─────────────────────────────────────

# Match: import ... from './path' or require('./path')
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)

_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def _resolve_js_import(import_path: str, source_file: Path, root: Path) -> Path | None:
    """Resolve a JS/TS import path to an actual file."""
    # Only check relative imports (./foo, ../foo)
    if not import_path.startswith("."):
        return None  # npm package — skip

    source_dir = source_file.parent
    target = (source_dir / import_path).resolve()

    # Try exact match
    if target.is_file():
        return target

    # Try with extensions
    for ext in _JS_EXTS:
        candidate = target.with_suffix(ext)
        if candidate.exists():
            return candidate

    # Try index files
    if target.is_dir():
        for ext in _JS_EXTS:
            idx = target / f"index{ext}"
            if idx.exists():
                return idx

    return None


def _get_js_files(root: Path) -> list[Path]:
    """Get all JS/TS files in the project."""
    files: list[Path] = []
    for f in root.rglob("*"):
        if f.is_file() and f.suffix in _JS_EXTS:
            rel = str(f.relative_to(root))
            if not any(skip in rel for skip in ["node_modules", ".adelie", "__pycache__", ".git"]):
                files.append(f)
    return files


def _check_js_imports(
    file_path: Path, content: str, root: Path,
) -> list[ImportIssue]:
    """Check JS/TS imports in a single file."""
    issues: list[ImportIssue] = []

    for line_num, line in enumerate(content.splitlines(), 1):
        for match in _JS_IMPORT_RE.finditer(line):
            import_path = match.group(1) or match.group(2)
            if not import_path or not import_path.startswith("."):
                continue  # Skip npm packages

            resolved = _resolve_js_import(import_path, file_path, root)
            if resolved is None:
                issues.append(ImportIssue(
                    file=str(file_path.relative_to(root)),
                    line=line_num,
                    imported=import_path,
                    reason=f"Local import '{import_path}' does not resolve to any file",
                ))

    return issues


# ── Public API ────────────────────────────────────────────────────────────────


def check_imports(
    files: list[dict],
    staging_root: Path,
    project_root: Path,
) -> list[ImportIssue]:
    """
    Check import consistency across staged files.

    Args:
        files: list of {"filepath": ...} dicts (staged files)
        staging_root: where staged files are
        project_root: the actual project root (for resolving existing modules)

    Returns:
        List of ImportIssue describing broken imports.
    """
    all_issues: list[ImportIssue] = []

    # Collect both staged and existing files for module resolution
    py_modules = _get_python_files(project_root)
    if staging_root.exists():
        py_modules.update(_get_python_files(staging_root))

    for finfo in files:
        filepath = finfo.get("filepath", "")
        if not filepath:
            continue

        # Check staged version first, fall back to project
        full_path = staging_root / filepath
        if not full_path.exists():
            full_path = project_root / filepath
        if not full_path.exists():
            continue

        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            continue

        ext = full_path.suffix.lower()

        if ext == ".py":
            issues = _check_python_imports(full_path, content, py_modules)
            all_issues.extend(issues)
        elif ext in _JS_EXTS:
            # For JS, resolve against both staging and project root
            issues = _check_js_imports(full_path, content, staging_root)
            if issues:
                # Retry against project root — import might resolve there
                issues2 = _check_js_imports(full_path, content, project_root)
                # Only keep issues that fail in BOTH locations
                staging_imports = {i.imported for i in issues}
                project_imports = {i.imported for i in issues2}
                truly_broken = staging_imports & project_imports
                all_issues.extend(i for i in issues if i.imported in truly_broken)

    return all_issues


def format_import_issues(issues: list[ImportIssue]) -> str:
    """Format import issues as a feedback string for Coder AI."""
    if not issues:
        return ""

    lines = [
        f"## ⚠️ IMPORT CONSISTENCY ERRORS ({len(issues)} issue(s))",
        "Fix these broken imports — they will cause build/runtime failures:",
        "",
    ]
    for issue in issues:
        line_info = f" (line {issue.line})" if issue.line else ""
        lines.append(f"- `{issue.file}`{line_info}: {issue.reason}")

    lines.append("")
    lines.append("Fix ALL import paths to reference files that actually exist in the project.")
    return "\n".join(lines)
