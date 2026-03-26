"""Adelie — Self-communicating autonomous AI loop system."""

from pathlib import Path as _Path
import json as _json

def _get_version() -> str:
    """Read version from package.json (single source of truth)."""
    try:
        pkg = _Path(__file__).resolve().parent.parent / "package.json"
        if pkg.exists():
            return _json.loads(pkg.read_text(encoding="utf-8")).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"

__version__ = "0.2.11"
