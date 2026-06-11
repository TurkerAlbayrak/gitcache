"""Git operations: clone (with progress), worktrees, fetch/pull, branches.

Uses GitPython when available for nicer clone progress, and always falls back
to plain ``git`` via subprocess so the tool works with only a system git.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

try:  # optional dependency
    import git  # type: ignore
    from git import RemoteProgress  # type: ignore

    _HAS_GITPYTHON = True
except ImportError:  # pragma: no cover
    git = None  # type: ignore
    RemoteProgress = object  # type: ignore
    _HAS_GITPYTHON = False


class GitError(RuntimeError):
    """Raised when a git operation fails."""


# Callback signature: (fraction_complete: float|None, message: str)
ProgressCallback = Callable[[Optional[float], str], None]


def repo_name_from_url(url: str) -> str:
    """Derive a sensible repo name from a clone URL or owner/name string."""
    cleaned = url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    # owner/name shorthand
    if "://" not in cleaned and "@" not in cleaned and cleaned.count("/") == 1:
        return cleaned.split("/")[-1]
    if "://" in cleaned:
        path = urlparse(cleaned).path
    elif ":" in cleaned:  # scp-like git@github.com:owner/name
        path = cleaned.split(":", 1)[1]
    else:
        path = cleaned
    return path.rstrip("/").split("/")[-1] or "repo"


def normalize_url(value: str) -> str:
    """Accept owner/name shorthand and turn it into an https clone URL."""
    if "://" in value or value.startswith("git@"):
        return value
    if value.count("/") == 1 and " " not in value:
        return f"https://github.com/{value}.git"
    return value


# ----------------------------------------------------------------------
# Subprocess helper
# ----------------------------------------------------------------------
def _run(args: List[str], cwd: Optional[Path] = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


if _HAS_GITPYTHON:

    class _RichProgress(RemoteProgress):  # type: ignore
        def __init__(self, callback: ProgressCallback) -> None:
            super().__init__()
            self._cb = callback

        def update(self, op_code, cur_count, max_count=None, message=""):
            frac = None
            if max_count:
                try:
                    frac = float(cur_count) / float(max_count)
                except (TypeError, ZeroDivisionError):
                    frac = None
            self._cb(frac, message or self._cur_line or "")


# ----------------------------------------------------------------------
# Public operations
# ----------------------------------------------------------------------
def clone(
    url: str,
    dest: Path,
    progress: Optional[ProgressCallback] = None,
) -> Path:
    """Clone *url* into *dest*. Returns the destination path."""
    url = normalize_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and any(dest.iterdir()):
        raise GitError(f"Destination already exists and is not empty: {dest}")

    if _HAS_GITPYTHON and progress is not None:
        try:
            git.Repo.clone_from(url, str(dest), progress=_RichProgress(progress))
            return dest
        except git.GitCommandError as exc:  # type: ignore
            raise GitError(str(exc.stderr or exc).strip())

    # Subprocess fallback: stream output and parse percentages for progress.
    _clone_subprocess(url, dest, progress)
    return dest


def _clone_subprocess(
    url: str, dest: Path, progress: Optional[ProgressCallback]
) -> None:
    proc = subprocess.Popen(
        ["git", "clone", "--progress", url, str(dest)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    pct_re = re.compile(r"(\d+)%")
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if progress and line:
            m = pct_re.search(line)
            frac = int(m.group(1)) / 100.0 if m else None
            progress(frac, line)
    proc.wait()
    if proc.returncode != 0:
        raise GitError(f"git clone failed for {url}")


def fetch(repo_path: Path) -> str:
    """Fetch all remotes for a repo."""
    return _run(["fetch", "--all", "--prune"], cwd=repo_path)


def pull(repo_path: Path) -> str:
    """Fast-forward pull the current branch."""
    return _run(["pull", "--ff-only"], cwd=repo_path)


def get_origin_url(repo_path: Path) -> Optional[str]:
    try:
        return _run(["config", "--get", "remote.origin.url"], cwd=repo_path)
    except GitError:
        return None


def current_branch(repo_path: Path) -> str:
    return _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)


def list_branches(repo_path: Path) -> List[str]:
    out = _run(["branch", "--format=%(refname:short)"], cwd=repo_path)
    return [b.strip() for b in out.splitlines() if b.strip()]


def branch_exists(repo_path: Path, branch: str) -> bool:
    # Checks local + remote-tracking refs.
    local = _run(["branch", "--list", branch], cwd=repo_path)
    if local.strip():
        return True
    remote = _run(["branch", "--list", "-r", f"origin/{branch}"], cwd=repo_path)
    return bool(remote.strip())


def add_worktree(
    repo_path: Path, worktree_path: Path, branch: str, create: bool
) -> None:
    """Add a git worktree for *branch* at *worktree_path*.

    If *create* is True a new branch is created off the current HEAD; otherwise
    an existing (possibly remote) branch is checked out.
    """
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if create:
        _run(
            ["worktree", "add", "-b", branch, str(worktree_path)],
            cwd=repo_path,
        )
    else:
        _run(["worktree", "add", str(worktree_path), branch], cwd=repo_path)


def list_worktrees(repo_path: Path) -> List[Tuple[str, str]]:
    """Return [(path, branch), ...] from ``git worktree list``."""
    out = _run(["worktree", "list", "--porcelain"], cwd=repo_path)
    results: List[Tuple[str, str]] = []
    cur_path = None
    cur_branch = ""
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur_path = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            cur_branch = line.split(" ", 1)[1].replace("refs/heads/", "")
        elif line == "":
            if cur_path:
                results.append((cur_path, cur_branch))
            cur_path, cur_branch = None, ""
    if cur_path:
        results.append((cur_path, cur_branch))
    return results


def remove_worktree(repo_path: Path, worktree_path: Path, force: bool = False) -> None:
    args = ["worktree", "remove", str(worktree_path)]
    if force:
        args.append("--force")
    _run(args, cwd=repo_path)
