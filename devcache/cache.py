"""Fast local cache index backed by SQLite.

Tracks every cached repository and its worktrees so the CLI can answer
"where is X / when did I last use it / what branches exist" instantly without
touching the filesystem or network.
"""

from __future__ import annotations

import difflib
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from devcache import config


@dataclass
class Repo:
    name: str
    path: str
    origin_url: Optional[str]
    last_opened: Optional[float]
    created_at: float

    @property
    def last_opened_str(self) -> str:
        if not self.last_opened:
            return "never"
        return _humanize_age(self.last_opened)


@dataclass
class Worktree:
    repo_name: str
    branch: str
    path: str
    created_at: float


def _humanize_age(ts: float) -> str:
    delta = max(0, int(time.time() - ts))
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= secs:
            return f"{delta // secs}{unit} ago"
    return "just now"


class Cache:
    """Thin wrapper around the SQLite index database."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or str(config.db_path())
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS repos (
                name        TEXT PRIMARY KEY,
                path        TEXT NOT NULL,
                origin_url  TEXT,
                last_opened REAL,
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS worktrees (
                repo_name  TEXT NOT NULL,
                branch     TEXT NOT NULL,
                path       TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (repo_name, branch),
                FOREIGN KEY (repo_name) REFERENCES repos(name) ON DELETE CASCADE
            );
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Repo CRUD
    # ------------------------------------------------------------------
    def add_repo(self, name: str, path: str, origin_url: Optional[str]) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO repos (name, path, origin_url, last_opened, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                path = excluded.path,
                origin_url = COALESCE(excluded.origin_url, repos.origin_url)
            """,
            (name, path, origin_url, None, now),
        )
        self._conn.commit()

    def get_repo(self, name: str) -> Optional[Repo]:
        row = self._conn.execute(
            "SELECT * FROM repos WHERE name = ?", (name,)
        ).fetchone()
        return _row_to_repo(row) if row else None

    def list_repos(self) -> List[Repo]:
        rows = self._conn.execute(
            "SELECT * FROM repos "
            "ORDER BY (last_opened IS NULL) ASC, last_opened DESC, name ASC"
        ).fetchall()
        return [_row_to_repo(r) for r in rows]

    def touch_repo(self, name: str) -> None:
        """Update the last-opened timestamp."""
        self._conn.execute(
            "UPDATE repos SET last_opened = ? WHERE name = ?", (time.time(), name)
        )
        self._conn.commit()

    def delete_repo(self, name: str) -> None:
        self._conn.execute("DELETE FROM repos WHERE name = ?", (name,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Worktree CRUD
    # ------------------------------------------------------------------
    def add_worktree(self, repo_name: str, branch: str, path: str) -> None:
        self._conn.execute(
            """
            INSERT INTO worktrees (repo_name, branch, path, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repo_name, branch) DO UPDATE SET path = excluded.path
            """,
            (repo_name, branch, path, time.time()),
        )
        self._conn.commit()

    def list_worktrees(self, repo_name: str) -> List[Worktree]:
        rows = self._conn.execute(
            "SELECT * FROM worktrees WHERE repo_name = ? ORDER BY created_at ASC",
            (repo_name,),
        ).fetchall()
        return [
            Worktree(r["repo_name"], r["branch"], r["path"], r["created_at"])
            for r in rows
        ]

    def get_worktree(self, repo_name: str, branch: str) -> Optional[Worktree]:
        row = self._conn.execute(
            "SELECT * FROM worktrees WHERE repo_name = ? AND branch = ?",
            (repo_name, branch),
        ).fetchone()
        if not row:
            return None
        return Worktree(row["repo_name"], row["branch"], row["path"], row["created_at"])

    def delete_worktree(self, repo_name: str, branch: str) -> None:
        self._conn.execute(
            "DELETE FROM worktrees WHERE repo_name = ? AND branch = ?",
            (repo_name, branch),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def find_best(self, query: str) -> Optional[Repo]:
        """Return the single closest matching repo (exact > substring > fuzzy)."""
        matches = self.search(query)
        return matches[0] if matches else None

    def search(self, query: str, limit: int = 10) -> List[Repo]:
        """Rank cached repos against *query* using a layered strategy."""
        query_l = query.lower()
        repos = self.list_repos()
        scored: List[tuple] = []
        for repo in repos:
            name_l = repo.name.lower()
            if name_l == query_l:
                score = 1.0
            elif name_l.startswith(query_l):
                score = 0.9
            elif query_l in name_l:
                score = 0.8
            else:
                score = difflib.SequenceMatcher(None, query_l, name_l).ratio()
            scored.append((score, repo))
        scored.sort(key=lambda x: (-x[0], x[1].name))
        # Drop very weak fuzzy matches to avoid nonsense suggestions.
        return [repo for score, repo in scored if score >= 0.4][:limit]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _row_to_repo(row: sqlite3.Row) -> Repo:
    return Repo(
        name=row["name"],
        path=row["path"],
        origin_url=row["origin_url"],
        last_opened=row["last_opened"],
        created_at=row["created_at"],
    )
