import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env — prioritize .adelie/.env, then project root .env
_user_cwd = Path(os.environ.get("ADELIE_CWD", os.getcwd())).resolve()
_adelie_env = _user_cwd / ".adelie" / ".env"
_root_env = _user_cwd / ".env"

if _adelie_env.exists():
    load_dotenv(_adelie_env)
elif _root_env.exists():
    load_dotenv(_root_env)
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
OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "")  # For Ollama Cloud

# ── Model Fallback ───────────────────────────────────────────────────────────
# Comma-separated fallback chain, e.g. "gemini:gemini-2.5-flash,gemini:gemini-2.0-flash,ollama:llama3.2"
# If empty, uses LLM_PROVIDER + its model as the single candidate.
FALLBACK_MODELS: str = os.getenv("FALLBACK_MODELS", "")
# How long (seconds) to skip a model after it fails with a retryable error
FALLBACK_COOLDOWN_SECONDS: int = int(os.getenv("FALLBACK_COOLDOWN_SECONDS", "60"))

# ── Loop ─────────────────────────────────────────────────────────────────────
LOOP_INTERVAL_SECONDS: int = int(os.getenv("LOOP_INTERVAL_SECONDS", "30"))

# ── Language ─────────────────────────────────────────────────────────────────
LANGUAGE: str = os.getenv("ADELIE_LANGUAGE", "ko")  # "ko" or "en"

# ── Browser Search Fallback ──────────────────────────────────────────────────
BROWSER_SEARCH_ENABLED: bool = os.getenv("BROWSER_SEARCH_ENABLED", "true").lower() in ("true", "1", "yes")
BROWSER_SEARCH_MAX_PAGES: int = int(os.getenv("BROWSER_SEARCH_MAX_PAGES", "3"))

# ── Plan Mode ────────────────────────────────────────────────────────────────
# When enabled, code changes require user approval before execution
PLAN_MODE_ENABLED: bool = os.getenv("PLAN_MODE", "false").lower() in ("true", "1", "yes")

# ── Sandbox Mode ─────────────────────────────────────────────────────────────
# "none" = no sandbox, "seatbelt" = macOS sandbox-exec, "docker" = Docker container
SANDBOX_MODE: str = os.getenv("SANDBOX_MODE", "none").lower()

# ── MCP (Model Context Protocol) ────────────────────────────────────────────
MCP_ENABLED: bool = os.getenv("MCP_ENABLED", "true").lower() in ("true", "1", "yes")

# ── Dashboard ───────────────────────────────────────────────────────────────
DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "5042"))
DASHBOARD_ENABLED: bool = os.getenv("DASHBOARD_ENABLED", "true").lower() in ("true", "1", "yes")

# ── Knowledge Base workspace ─────────────────────────────────────────────────
_ws_env = os.getenv("WORKSPACE_PATH")
if _ws_env:
    WORKSPACE_PATH: Path = Path(_ws_env).resolve()
else:
    # Resolve relative to user's working directory, not Python process cwd
    WORKSPACE_PATH: Path = (_user_cwd / ".adelie" / "workspace").resolve()

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
