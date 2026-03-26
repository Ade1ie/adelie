"""
adelie/commands/__init__.py

Re-exports common helpers so any code that previously did
  from adelie.cli import _find_workspace_root
can do:
  from adelie.commands import _find_workspace_root
"""

from adelie.commands._helpers import (
    _find_workspace_root,
    _workspace_config_path,
    _load_workspace_config,
    _save_workspace_config,
    _update_env_file,
    _setup_env_from_workspace,
    _ensure_adelie_config,
    _validate_provider,
    _detect_os,
    _generate_os_context,
    _auto_generate_goal,
)

__all__ = [
    "_find_workspace_root",
    "_workspace_config_path",
    "_load_workspace_config",
    "_save_workspace_config",
    "_update_env_file",
    "_setup_env_from_workspace",
    "_ensure_adelie_config",
    "_validate_provider",
    "_detect_os",
    "_generate_os_context",
    "_auto_generate_goal",
]
