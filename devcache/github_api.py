"""GitHub integration.

Resolution order for everything (auth, repo listing, URL lookup):

1. The official ``gh`` CLI if it is installed and authenticated.
2. The GitHub REST API via ``requests`` (or stdlib ``urllib`` as a fallback),
   using a token from config / environment.

This keeps the tool useful whether or not the user has ``gh`` or ``requests``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from devcache.config import Config

try:  # optional dependency
    import requests  # type: ignore

    _HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    requests = None  # type: ignore
    _HAS_REQUESTS = False

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised when a GitHub operation fails."""


@dataclass
class RemoteRepo:
    name: str
    full_name: str
    clone_url: str
    ssh_url: str
    description: Optional[str]
    private: bool


def gh_cli_available() -> bool:
    return shutil.which("gh") is not None


def _gh(*args: str) -> str:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitHubError(proc.stderr.strip() or "gh command failed")
    return proc.stdout


class GitHubAPI:
    def __init__(self, config: Config) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def login(self, token: str) -> str:
        """Validate *token* and return the authenticated username."""
        data = self._request("GET", "/user", token=token)
        user = data.get("login")
        if not user:
            raise GitHubError("Could not determine the authenticated user.")
        return user

    def whoami(self) -> Optional[str]:
        if self.config.token:
            try:
                return self._request("GET", "/user").get("login")
            except GitHubError:
                pass
        if gh_cli_available():
            try:
                out = _gh("api", "user", "--jq", ".login")
                return out.strip() or None
            except GitHubError:
                pass
        return None

    # ------------------------------------------------------------------
    # Repo discovery
    # ------------------------------------------------------------------
    def list_repos(self, user: Optional[str] = None) -> List[RemoteRepo]:
        """List repositories for the authenticated user (or a given user)."""
        # Prefer authenticated listing (includes private repos).
        if user is None and (self.config.token or gh_cli_available()):
            return self._list_authenticated_repos()
        target = user or self.config.github_user
        if not target:
            raise GitHubError(
                "No GitHub user configured. Run 'dev auth login' first."
            )
        repos: List[RemoteRepo] = []
        page = 1
        while True:
            batch = self._request(
                "GET", f"/users/{target}/repos?per_page=100&page={page}"
            )
            if not batch:
                break
            repos.extend(_parse_repo(r) for r in batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    def _list_authenticated_repos(self) -> List[RemoteRepo]:
        if self.config.token:
            repos: List[RemoteRepo] = []
            page = 1
            while True:
                batch = self._request(
                    "GET",
                    f"/user/repos?per_page=100&page={page}&affiliation=owner",
                )
                if not batch:
                    break
                repos.extend(_parse_repo(r) for r in batch)
                if len(batch) < 100:
                    break
                page += 1
            return repos
        # Fall back to gh CLI.
        out = _gh(
            "repo",
            "list",
            "--limit",
            "1000",
            "--json",
            "name,nameWithOwner,url,sshUrl,description,isPrivate",
        )
        data = json.loads(out or "[]")
        return [
            RemoteRepo(
                name=r["name"],
                full_name=r["nameWithOwner"],
                clone_url=r["url"] + ".git" if not r["url"].endswith(".git") else r["url"],
                ssh_url=r.get("sshUrl", ""),
                description=r.get("description"),
                private=r.get("isPrivate", False),
            )
            for r in data
        ]

    def resolve_repo_url(self, name: str) -> Optional[str]:
        """Find a clone URL for a repo by (case-insensitive) name."""
        try:
            repos = self.list_repos()
        except GitHubError:
            return None
        name_l = name.lower()
        for repo in repos:
            if repo.name.lower() == name_l:
                return repo.clone_url
        # Allow owner/name syntax to map straight to a URL.
        if "/" in name:
            return f"https://github.com/{name}.git"
        return None

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------
    def _headers(self, token: Optional[str]) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "devcache-cli",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, endpoint: str, token: Optional[str] = None):
        tok = token or self.config.token
        url = endpoint if endpoint.startswith("http") else API_ROOT + endpoint
        headers = self._headers(tok)

        if _HAS_REQUESTS:
            resp = requests.request(method, url, headers=headers, timeout=20)
            if resp.status_code == 401:
                raise GitHubError("Authentication failed (401). Check your token.")
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                raise GitHubError(
                    "GitHub API rate limit exceeded. Authenticate with 'dev auth login'."
                )
            if resp.status_code >= 400:
                raise GitHubError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
            return resp.json()

        # Stdlib fallback.
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover
            if exc.code == 401:
                raise GitHubError("Authentication failed (401). Check your token.")
            if exc.code == 403:
                raise GitHubError(
                    "GitHub API rate limit / forbidden. Authenticate with 'dev auth login'."
                )
            raise GitHubError(f"GitHub API error {exc.code}: {exc.reason}")
        except urllib.error.URLError as exc:  # pragma: no cover
            raise GitHubError(f"Network error contacting GitHub: {exc.reason}")


def _parse_repo(data: dict) -> RemoteRepo:
    return RemoteRepo(
        name=data["name"],
        full_name=data.get("full_name", data["name"]),
        clone_url=data.get("clone_url", ""),
        ssh_url=data.get("ssh_url", ""),
        description=data.get("description"),
        private=data.get("private", False),
    )
