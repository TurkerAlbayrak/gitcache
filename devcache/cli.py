"""Command-line interface for DevCache.

Defines the argument parser, dispatches subcommands, and implements each
command handler by orchestrating the cache, git, and GitHub modules.

Commands:
    dev open <repo> [--editor E] [--no-open] [--url URL]
    dev list
    dev search <query>
    dev branch <name> [--repo R] [--editor E] [--no-open]
    dev delete <repo> [--yes]
    dev sync [repo]
    dev auth (login | status | logout)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from devcache import __version__, ui
from devcache.cache import Cache
from devcache.config import Config, repos_dir, worktrees_dir
from devcache.github_api import GitHubAPI, GitHubError, gh_cli_available
from devcache import git_manager as gm


# ======================================================================
# Helpers
# ======================================================================
def _slug(value: str) -> str:
    """Filesystem-safe slug for branch/worktree folder names."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "branch"


def _launch_editor(config: Config, editor: Optional[str], path: Path) -> bool:
    """Open *path* in the chosen editor. Returns True on success."""
    command = config.resolve_editor(editor)
    try:
        # On Windows, VSCode's launcher is `code.cmd`; shell=True helps resolve it.
        if os.name == "nt":
            subprocess.Popen(f'{command} "{path}"', shell=True)
        else:
            subprocess.Popen([command, str(path)])
        return True
    except FileNotFoundError:
        ui.error(f"Editor '{command}' not found on PATH.")
        ui.hint("Configure editors in ~/.devcache/config.json or pass --editor.")
        return False
    except OSError as exc:  # pragma: no cover
        ui.error(f"Failed to launch editor: {exc}")
        return False


def _resolve_repo(cache: Cache, query: str):
    """Find a cached repo by exact name, else fuzzy match (with confirmation)."""
    repo = cache.get_repo(query)
    if repo:
        return repo
    best = cache.find_best(query)
    if best and best.name.lower() != query.lower():
        ui.info(f"No exact match for '{query}'. Closest: [bold]{best.name}[/]")
        if ui.confirm(f"Open '{best.name}'?", default=True):
            return best
        return None
    return best


# ======================================================================
# Command handlers
# ======================================================================
def cmd_open(args: argparse.Namespace) -> int:
    config = Config.load()
    with Cache() as cache:
        repo = _resolve_repo(cache, args.repo)

        # Not cached -> try to clone it.
        if repo is None:
            url = args.url
            if not url:
                url = _discover_url(config, args.repo)
            if not url:
                ui.error(f"Repo '{args.repo}' not found locally or on GitHub.")
                ui.hint("Provide a URL: dev open <name> --url <git-url>")
                ui.hint("Or authenticate: dev auth login")
                return 1
            name = gm.repo_name_from_url(url) if args.url else args.repo
            dest = repos_dir() / name
            ui.info(f"Cloning [bold]{name}[/] from {gm.normalize_url(url)}")
            try:
                with ui.clone_progress("Cloning") as progress:
                    task = progress.add_task("Cloning", total=1.0)

                    def on_progress(frac, message):
                        if frac is not None:
                            progress.update(task, completed=frac)

                    gm.clone(url, dest, progress=on_progress)
                    progress.update(task, completed=1.0)
            except gm.GitError as exc:
                ui.error(f"Clone failed: {exc}")
                return 1
            origin = gm.get_origin_url(dest)
            cache.add_repo(name, str(dest), origin)
            repo = cache.get_repo(name)
            ui.success(f"Cached [bold]{name}[/] at {dest}")

        # Open (unless suppressed).
        cache.touch_repo(repo.name)
        path = Path(repo.path)
        if not path.exists():
            ui.error(f"Cached path is missing: {path}")
            ui.hint(f"Re-clone with: dev delete {repo.name} && dev open {repo.name}")
            return 1
        if args.no_open:
            ui.success(f"{repo.name} -> {path}")
            return 0
        if _launch_editor(config, args.editor, path):
            ui.success(f"Opened [bold]{repo.name}[/] in {config.resolve_editor(args.editor)}")
        return 0


def _discover_url(config: Config, name: str) -> Optional[str]:
    """Best-effort lookup of a clone URL via GitHub."""
    if "/" in name or "://" in name:
        return name  # treat as URL / owner-name shorthand
    api = GitHubAPI(config)
    if not (config.token or gh_cli_available() or config.github_user):
        return None
    try:
        with ui.spinner(f"Searching GitHub for '{name}'"):
            return api.resolve_repo_url(name)
    except GitHubError as exc:
        ui.warn(f"GitHub lookup failed: {exc}")
        return None


def cmd_list(args: argparse.Namespace) -> int:
    with Cache() as cache:
        repos = cache.list_repos()
        rows = []
        for repo in repos:
            branches = len(cache.list_worktrees(repo.name)) + 1
            rows.append((repo.name, branches, repo.last_opened_str, repo.origin_url))
        ui.repo_table(rows)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    with Cache() as cache:
        results = cache.search(args.query)
        ui.search_results(results)
    return 0 if results else 1


def cmd_branch(args: argparse.Namespace) -> int:
    config = Config.load()
    with Cache() as cache:
        # Determine which repo to branch from.
        if args.repo:
            repo = _resolve_repo(cache, args.repo)
        else:
            repo = _infer_repo_from_cwd(cache) or _most_recent(cache)
        if repo is None:
            ui.error("Could not determine which repo to branch.")
            ui.hint("Specify one: dev branch <name> --repo <repo>")
            return 1

        repo_path = Path(repo.path)
        if not repo_path.exists():
            ui.error(f"Repo path missing: {repo_path}")
            return 1

        branch = args.name
        wt_path = worktrees_dir() / repo.name / _slug(branch)

        existing = cache.get_worktree(repo.name, branch)
        if existing and Path(existing.path).exists():
            ui.info(f"Worktree for '{branch}' already exists.")
            if not args.no_open:
                _launch_editor(config, args.editor, Path(existing.path))
            return 0

        create = not gm.branch_exists(repo_path, branch)
        try:
            with ui.spinner(f"Creating worktree for '{branch}'"):
                gm.add_worktree(repo_path, wt_path, branch, create=create)
        except gm.GitError as exc:
            ui.error(f"Failed to create worktree: {exc}")
            return 1

        cache.add_worktree(repo.name, branch, str(wt_path))
        verb = "Created new branch" if create else "Checked out branch"
        ui.success(f"{verb} [bold]{branch}[/] at {wt_path}")
        if not args.no_open:
            _launch_editor(config, args.editor, wt_path)
        return 0


def _infer_repo_from_cwd(cache: Cache):
    cwd = Path.cwd().resolve()
    for repo in cache.list_repos():
        try:
            rp = Path(repo.path).resolve()
        except OSError:
            continue
        if cwd == rp or rp in cwd.parents:
            return repo
    return None


def _most_recent(cache: Cache):
    repos = cache.list_repos()
    return repos[0] if repos else None


def cmd_delete(args: argparse.Namespace) -> int:
    import shutil

    with Cache() as cache:
        repo = cache.get_repo(args.repo) or _resolve_repo(cache, args.repo)
        if repo is None:
            ui.error(f"No cached repo named '{args.repo}'.")
            return 1

        if not args.yes:
            if not ui.confirm(
                f"Delete '{repo.name}' and all its worktrees from disk?",
                default=False,
            ):
                ui.info("Aborted.")
                return 0

        # Remove worktrees first (folders + index rows).
        for wt in cache.list_worktrees(repo.name):
            wt_path = Path(wt.path)
            try:
                if wt_path.exists():
                    gm.remove_worktree(Path(repo.path), wt_path, force=True)
            except gm.GitError:
                pass
            if wt_path.exists():
                shutil.rmtree(wt_path, ignore_errors=True)

        repo_path = Path(repo.path)
        if repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)
        # Clean up empty worktree parent dir.
        wt_parent = worktrees_dir() / repo.name
        if wt_parent.exists():
            shutil.rmtree(wt_parent, ignore_errors=True)

        cache.delete_repo(repo.name)
        ui.success(f"Deleted [bold]{repo.name}[/].")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    with Cache() as cache:
        if args.repo:
            repo = _resolve_repo(cache, args.repo)
            repos = [repo] if repo else []
        else:
            repos = cache.list_repos()
        if not repos:
            ui.warn("Nothing to sync.")
            return 1

        failures = 0
        for repo in repos:
            path = Path(repo.path)
            if not path.exists():
                ui.warn(f"{repo.name}: path missing, skipping.")
                failures += 1
                continue
            try:
                with ui.spinner(f"Syncing {repo.name}"):
                    gm.fetch(path)
                    try:
                        gm.pull(path)
                    except gm.GitError:
                        # Non-fast-forward or detached HEAD: fetch is still useful.
                        pass
                ui.success(f"Synced [bold]{repo.name}[/]")
            except gm.GitError as exc:
                ui.error(f"{repo.name}: {exc}")
                failures += 1
    return 0 if failures == 0 else 1


def cmd_auth(args: argparse.Namespace) -> int:
    config = Config.load()
    api = GitHubAPI(config)

    if args.auth_command == "status":
        user = api.whoami()
        if user:
            source = "config token" if config.github_token else (
                "environment token" if config.token else "gh CLI"
            )
            ui.success(f"Authenticated as [bold]{user}[/] (via {source}).")
            return 0
        ui.warn("Not authenticated. Run: dev auth login")
        return 1

    if args.auth_command == "logout":
        config.github_token = None
        config.save()
        ui.success("Removed stored GitHub token.")
        return 0

    # login (default)
    ui.banner()
    if gh_cli_available() and not args.token:
        ui.info("GitHub CLI detected. You can also use it directly via 'gh auth login'.")
    token = args.token or ui.ask(
        "Paste a GitHub personal access token (scopes: repo)", password=True
    )
    if not token:
        ui.error("No token provided.")
        return 1
    try:
        with ui.spinner("Verifying token"):
            user = api.login(token)
    except GitHubError as exc:
        ui.error(str(exc))
        return 1
    config.github_token = token
    config.github_user = user
    config.save()
    ui.success(f"Logged in as [bold]{user}[/]. Token saved to ~/.devcache/config.json")
    return 0


# ======================================================================
# Parser
# ======================================================================
EXAMPLES = """
examples:
  dev open myrepo                  open a cached repo (or clone it via GitHub)
  dev open owner/name              clone by owner/name shorthand
  dev open api --editor nvim       fuzzy-match 'api' and open in Neovim
  dev open proj --url <git-url>    clone from an explicit URL
  dev list                         list all cached repositories
  dev search ape                   fuzzy search cached repos
  dev branch feature-x             create a worktree for a new branch
  dev sync                         fetch + pull every cached repo
  dev auth login                   store a GitHub token
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev",
        description="DevCache - a fast, local GitHub repository manager.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"devcache {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # open
    p_open = sub.add_parser("open", help="Open (clone if needed) a repository")
    p_open.add_argument("repo", help="Repo name, owner/name, or URL")
    p_open.add_argument("--url", help="Explicit clone URL (skips GitHub lookup)")
    p_open.add_argument("-e", "--editor", help="Editor: code, nvim, vim, subl, cursor...")
    p_open.add_argument(
        "--no-open", action="store_true", help="Cache only; do not launch an editor"
    )
    p_open.set_defaults(func=cmd_open)

    # list
    p_list = sub.add_parser("list", help="List cached repositories")
    p_list.set_defaults(func=cmd_list)

    # search
    p_search = sub.add_parser("search", help="Fuzzy search cached repositories")
    p_search.add_argument("query", help="Search term")
    p_search.set_defaults(func=cmd_search)

    # branch
    p_branch = sub.add_parser("branch", help="Create/open a git worktree for a branch")
    p_branch.add_argument("name", help="Branch name")
    p_branch.add_argument("-r", "--repo", help="Target repo (defaults to cwd / most recent)")
    p_branch.add_argument("-e", "--editor", help="Editor to open the worktree in")
    p_branch.add_argument("--no-open", action="store_true", help="Do not launch an editor")
    p_branch.set_defaults(func=cmd_branch)

    # delete
    p_del = sub.add_parser("delete", help="Delete a cached repository from disk")
    p_del.add_argument("repo", help="Repo name")
    p_del.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_del.set_defaults(func=cmd_delete)

    # sync
    p_sync = sub.add_parser("sync", help="Fetch + pull cached repos")
    p_sync.add_argument("repo", nargs="?", help="Specific repo (default: all)")
    p_sync.set_defaults(func=cmd_sync)

    # auth
    p_auth = sub.add_parser("auth", help="Manage GitHub authentication")
    auth_sub = p_auth.add_subparsers(dest="auth_command", metavar="<action>")
    p_login = auth_sub.add_parser("login", help="Store a GitHub token")
    p_login.add_argument("--token", help="Provide token non-interactively")
    auth_sub.add_parser("status", help="Show authentication status")
    auth_sub.add_parser("logout", help="Remove the stored token")
    p_auth.set_defaults(func=cmd_auth, auth_command="login")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        ui.banner()
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover
        ui.error("Interrupted.")
        return 130
    except Exception as exc:  # last-resort guard for clean UX
        ui.error(f"Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
