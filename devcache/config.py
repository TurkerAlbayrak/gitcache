"""Configuration & filesystem layout for DevCache.

All persistent state lives under a single home directory (``~/.devcache`` by
default, overridable with the ``DEVCACHE_HOME`` environment variable):

    ~/.devcache/
        config.json        # user settings + GitHub credentials
        index.db           # SQLite cache index
        repos/             # cloned bare-ish repositories (main worktrees)
        worktrees/         # additional git worktrees (one folder per branch)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


def get_home() -> Path:
    """Return the DevCache home directory, creating the skeleton if needed."""
    env = os.environ.get("DEVCACHE_HOME")
    home = Path(env).expanduser() if env else Path.home() / ".devcache"
    home.mkdir(parents=True, exist_ok=True)
    (home / "repos").mkdir(exist_ok=True)
    (home / "worktrees").mkdir(exist_ok=True)
    return home


def repos_dir() -> Path:
    return get_home() / "repos"


def worktrees_dir() -> Path:
    return get_home() / "worktrees"


def db_path() -> Path:
    return get_home() / "index.db"


def config_path() -> Path:
    return get_home() / "config.json"


@dataclass
class Config:
    """User-facing settings, persisted as JSON."""

    github_user: Optional[str] = None
    github_token: Optional[str] = None
    default_editor: str = "code"
    # Map shorthand editor names to the actual executable/launch command.
    editors: Dict[str, str] = field(
        default_factory=lambda: {
            "code": "code",
            "vscode": "code",
            "nvim": "nvim",
            "vim": "vim",
            "subl": "subl",
            "sublime": "subl",
            "cursor": "cursor",
            "idea": "idea",
            "pycharm": "pycharm",
        }
    )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        cfg = cls()
        # Only adopt known fields so an old/corrupt file can't crash us.
        if isinstance(data.get("github_user"), str):
            cfg.github_user = data["github_user"]
        if isinstance(data.get("github_token"), str):
            cfg.github_token = data["github_token"]
        if isinstance(data.get("default_editor"), str):
            cfg.default_editor = data["default_editor"]
        if isinstance(data.get("editors"), dict):
            cfg.editors.update(data["editors"])
        return cfg

    def save(self) -> None:
        path = config_path()
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        # Best effort: tighten permissions since the token lives here.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def resolve_editor(self, name: Optional[str]) -> str:
        """Map an editor shorthand to its launch command."""
        key = (name or self.default_editor).lower()
        return self.editors.get(key, name or self.default_editor)

    @property
    def token(self) -> Optional[str]:
        """Token from config, falling back to common env vars."""
        return (
            self.github_token
            or os.environ.get("DEVCACHE_GITHUB_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
        )
