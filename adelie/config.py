import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from user's project directory first, then fallback to package root
_user_cwd = Path(os.environ.get("ADELIE_CWD", os.getcwd())).resolve()
_env_file = _user_cwd / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
else:
    load_dotenv()  # fallback: search from cwd upward

# ── LLM Provider ─────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" or "ollama"

# ── Gemini ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

# ── Model Fallback ───────────────────────────────────────────────────────────
# Comma-separated fallback chain, e.g. "gemini:gemini-2.5-flash,gemini:gemini-2.0-flash,ollama:llama3.2"
# If empty, uses LLM_PROVIDER + its model as the single candidate.
FALLBACK_MODELS: str = os.getenv("FALLBACK_MODELS", "")
# How long (seconds) to skip a model after it fails with a retryable error
FALLBACK_COOLDOWN_SECONDS: int = int(os.getenv("FALLBACK_COOLDOWN_SECONDS", "60"))

# ── Loop ─────────────────────────────────────────────────────────────────────
LOOP_INTERVAL_SECONDS: int = int(os.getenv("LOOP_INTERVAL_SECONDS", "30"))

# ── Browser Search Fallback ──────────────────────────────────────────────────
BROWSER_SEARCH_ENABLED: bool = os.getenv("BROWSER_SEARCH_ENABLED", "true").lower() in ("true", "1", "yes")
BROWSER_SEARCH_MAX_PAGES: int = int(os.getenv("BROWSER_SEARCH_MAX_PAGES", "3"))

# ── Knowledge Base workspace ─────────────────────────────────────────────────
WORKSPACE_PATH: Path = Path(os.getenv("WORKSPACE_PATH", "./.adelie/workspace")).resolve()

# ── Project paths ─────────────────────────────────────────────────────────────
# ADELIE_ROOT = .adelie/ — internal state (KB, coder logs, runner, tests, etc.)
# PROJECT_ROOT = parent of .adelie/ — the actual project where source code lives
ADELIE_ROOT: Path = WORKSPACE_PATH.parent     # .adelie/
PROJECT_ROOT: Path = ADELIE_ROOT.parent       # project root (where src/ lives)

# Canonical KB category folders
KB_CATEGORIES: list[str] = [
    "skills",
    "dependencies",
    "errors",
    "logic",
    "exports",
    "maintenance",
]

# Tags that map situations to relevant KB categories
SITUATION_CATEGORY_MAP: dict[str, list[str]] = {
    "error":       ["errors", "skills"],
    "new_logic":   ["skills", "dependencies", "logic"],
    "export":      ["exports", "logic"],
    "maintenance": ["maintenance", "logic"],
    "normal":      ["skills", "logic", "dependencies"],
}
