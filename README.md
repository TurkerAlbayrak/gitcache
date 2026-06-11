# DevCache

> A fast, local GitHub repository manager with caching, git worktrees, fuzzy search, and editor integration.

DevCache eliminates repeated `git clone` operations. Clone a repo once, and from
then on open it instantly by name — no URL required — from anywhere on your
machine. It tracks everything in a local SQLite index and uses **git worktrees**
so multiple branches live in separate folders without duplicating the repo.

<img width="961" height="701" alt="image" src="https://github.com/user-attachments/assets/79580f9d-3d25-4b07-9e94-1be2e09b7557" />


```bash
dev open myrepo          # already cached? opens instantly. not cached? clones it.
dev open api             # fuzzy-matches "api" -> "awesome-api-project"
dev branch feature-x     # spins up a worktree for a new branch and opens it
dev sync                 # fetch + pull every cached repo
```

---

## Features

| Feature | What it does |
| --- | --- |
| **Smart repo resolution** | `dev open <name>` searches the local cache, then GitHub, and auto-clones if needed — no URL required. |
| **GitHub integration** | Uses the `gh` CLI if present, otherwise the GitHub REST API with your token. `dev auth login` to authenticate. |
| **Git worktrees** | `dev branch <name>` creates a real `git worktree` in its own folder so branches never collide. |
| **Fast cache index** | SQLite database tracking name, path, origin URL, last-opened time, and branches. |
| **Fuzzy search** | `dev open api` / `dev search api` match the closest repo name. |
| **Editor flexibility** | `--editor code|nvim|vim|subl|cursor|...` (configurable). |
| **Polished UX** | Colored output, clone progress bars, spinners, and clean error handling via [`rich`](https://github.com/Textualize/rich). |
| **Global command** | Installs as `dev`, `devcache`, and `gitcache`. Cross-platform: Windows, macOS, Linux. |

---

## Installation

Requires **Python 3.8+** and **git** on your PATH.

### From GitHub (recommended)

Install directly from the repository — no PyPI account needed:

```bash
pip install git+https://github.com/TurkerAlbayrak/gitcache.git
```

With the recommended extras (GitPython for richer clone progress + requests):

```bash
pip install "gitcache[full] @ git+https://github.com/TurkerAlbayrak/gitcache.git"
```

Pin to a specific tag/branch/commit:

```bash
pip install git+https://github.com/TurkerAlbayrak/gitcache.git@v1.0.0
```

Upgrade to the latest version later:

```bash
pip install --upgrade --force-reinstall git+https://github.com/TurkerAlbayrak/gitcache.git
```

### From source (clone first)

```bash
git clone https://github.com/TurkerAlbayrak/gitcache.git
cd gitcache

pip install .            # core install
pip install ".[full]"    # with GitPython + requests
```

### From PyPI

> Not published yet. The name `devcache` was already taken, so the planned
> distribution name is `gitcache`:
>
> ```bash
> pip install gitcache
> ```

### What you get

All install methods register **three identical console commands** — use whichever you like:

```bash
dev --version
devcache --version
gitcache --version
```

> The only hard dependency is `rich`. `GitPython` and `requests` are optional —
> DevCache falls back to plain `git` (subprocess) and the stdlib `urllib` when
> they aren't installed.

### Development setup

```bash
git clone https://github.com/TurkerAlbayrak/gitcache.git
cd gitcache
pip install -e ".[full,dev]"     # editable install with dev tools (pytest, build)
```

### Uninstall

```bash
pip uninstall gitcache
```

---

## Quick start

```bash
# 1. (optional) authenticate so name-only cloning can find your repos
dev auth login

# 2. open a repo — clones on first use, instant afterwards
dev open my-service
dev open owner/some-repo          # owner/name shorthand
dev open proj --url https://github.com/owner/proj.git

# 3. list what you've cached
dev list

# 4. work on a feature branch in an isolated worktree
dev branch feature-login          # creates ~/.devcache/worktrees/<repo>/feature-login

# 5. keep everything fresh
dev sync                          # all repos
dev sync my-service               # one repo

# 6. clean up
dev delete my-service
```

### Command reference

```text
dev open <repo>      Open a repo by name/URL; clone it if not cached.
                     --url URL        explicit clone URL
                     --editor NAME    code | nvim | vim | subl | cursor | ...
                     --no-open        cache only, don't launch an editor
dev list             List all cached repositories.
dev search <query>   Fuzzy-search cached repositories.
dev branch <name>    Create/open a git worktree for a branch.
                     --repo R         target repo (defaults to cwd / most recent)
                     --editor NAME    editor to open the worktree in
                     --no-open        don't launch an editor
dev delete <repo>    Remove a cached repo (and its worktrees) from disk.
                     --yes            skip confirmation
dev sync [repo]      Fetch + pull a repo, or all repos if omitted.
dev auth login       Store a GitHub token (--token to pass non-interactively).
dev auth status      Show authentication status.
dev auth logout      Remove the stored token.
```

Run `dev --help` or `dev <command> --help` for full details and examples.

---

## Full walkthrough — a day with DevCache

A complete, copy-pasteable scenario that touches **every command**. The story:
you start fresh, authenticate, clone a project, work on two feature branches in
parallel via worktrees, keep things synced, and finally clean up.

```bash
# ──────────────────────────────────────────────────────────────────────
# 0. Sanity check — is it installed?
# ──────────────────────────────────────────────────────────────────────
dev --version                       # devcache 1.0.0
dev --help                          # see all commands + examples


# ──────────────────────────────────────────────────────────────────────
# 1. Authenticate with GitHub (enables name-only cloning of your repos)
# ──────────────────────────────────────────────────────────────────────
dev auth login                      # prompts for a Personal Access Token (repo scope)
# ...or non-interactively:
dev auth login --token ghp_xxxxxxxxxxxxxxxxxxxx

dev auth status                     # ✓ Authenticated as <you> (via config token)


# ──────────────────────────────────────────────────────────────────────
# 2. Open / clone a project (three equivalent styles)
# ──────────────────────────────────────────────────────────────────────
dev open octocat/Hello-World        # owner/name shorthand -> clones + opens in editor
# first run  : clones into ~/.devcache/repos/Hello-World (with a progress bar)
# next runs  : opens INSTANTLY from cache

dev open Hello-World                 # by name only (resolved via cache, then GitHub)
dev open demo --url https://github.com/octocat/Hello-World.git   # explicit URL

dev open Hello-World --editor nvim  # choose the editor (code | nvim | vim | subl | cursor)
dev open Hello-World --no-open      # cache only, don't launch an editor


# ──────────────────────────────────────────────────────────────────────
# 3. See what you have cached
# ──────────────────────────────────────────────────────────────────────
dev list
# ┌─────────────┬──────────┬─────────────┬───────────────────────────────────┐
# │ Repo        │ Branches │ Last opened │ Origin                            │
# ├─────────────┼──────────┼─────────────┼───────────────────────────────────┤
# │ Hello-World │    1     │ just now    │ https://github.com/octocat/...    │
# └─────────────┴──────────┴─────────────┴───────────────────────────────────┘


# ──────────────────────────────────────────────────────────────────────
# 4. Fuzzy search — you don't need the exact name
# ──────────────────────────────────────────────────────────────────────
dev search helo                     # matches "Hello-World"
dev open hello                      # closest match -> asks "Open 'Hello-World'? [y/n]"


# ──────────────────────────────────────────────────────────────────────
# 5. Work on feature branches IN PARALLEL using git worktrees
# ──────────────────────────────────────────────────────────────────────
dev branch feature-login            # new branch in its own folder, opens in editor
#   -> ~/.devcache/worktrees/Hello-World/feature-login

dev branch bugfix-typo --repo Hello-World --no-open   # second branch, no editor
#   -> ~/.devcache/worktrees/Hello-World/bugfix-typo
# Both worktrees share ONE object store: near-zero disk, instant setup.

dev list                            # now shows Branches = 3 (main + 2 worktrees)


# ──────────────────────────────────────────────────────────────────────
# 6. Keep everything up to date (fetch + pull)
# ──────────────────────────────────────────────────────────────────────
dev sync Hello-World                # sync one repo
dev sync                            # sync ALL cached repos at once


# ──────────────────────────────────────────────────────────────────────
# 7. Clean up
# ──────────────────────────────────────────────────────────────────────
dev delete Hello-World              # asks for confirmation, removes repo + worktrees
dev delete Hello-World --yes        # skip the confirmation prompt

dev auth logout                     # remove the stored token when you're done
```

### What happens on disk during this scenario

```
~/.devcache/
├── config.json                       # created by step 1 (auth login)
├── index.db                          # SQLite index, updated by every command
├── repos/
│   └── Hello-World/                  # step 2: the primary clone
└── worktrees/
    └── Hello-World/
        ├── feature-login/            # step 5: worktree #1
        └── bugfix-typo/              # step 5: worktree #2
```

> Tip: prefix any command with a custom `DEVCACHE_HOME` to experiment in an
> isolated sandbox without touching your real cache, e.g.
> `DEVCACHE_HOME=/tmp/dc dev open octocat/Hello-World` (Linux/macOS) or
> `$env:DEVCACHE_HOME="$env:TEMP\dc"; dev open octocat/Hello-World` (PowerShell).

---

## Authentication

DevCache looks for credentials in this order:

1. Token stored via `dev auth login` (saved to `~/.devcache/config.json`, `chmod 600`).
2. Environment: `DEVCACHE_GITHUB_TOKEN`, `GITHUB_TOKEN`, or `GH_TOKEN`.
3. The `gh` CLI, if installed and authenticated.

To create a token: GitHub → Settings → Developer settings → Personal access
tokens → grant the **`repo`** scope. You can also just rely on `gh auth login`.

---

## Architecture

DevCache is a small, modular package. Each module has one responsibility and the
CLI orchestrates them:

```
devcache/
├── __init__.py        Package metadata / version
├── __main__.py        Enables `python -m devcache`
├── config.py          Filesystem layout (~/.devcache) + user settings (config.json)
├── cache.py           SQLite index (repos + worktrees) and the fuzzy-search engine
├── github_api.py      GitHub access via `gh` CLI or REST API (requests / urllib)
├── git_manager.py     git operations: clone (+progress), worktrees, fetch/pull, branches
├── ui.py              All terminal output: rich tables, progress bars, prompts
└── cli.py             argparse parser + command handlers (the orchestration layer)
```

**Data flow for `dev open <name>`:**

```
cli.cmd_open
   ├─ cache.get_repo / cache.find_best   (1) is it cached? fuzzy match if not exact
   ├─ github_api.resolve_repo_url        (2) not cached -> find clone URL on GitHub
   ├─ git_manager.clone (+ ui progress)  (3) clone into ~/.devcache/repos/<name>
   ├─ cache.add_repo / touch_repo        (4) record it / bump last-opened
   └─ cli._launch_editor                 (5) open in the chosen editor
```

**On-disk layout** (created on first run, override with `DEVCACHE_HOME`):

```
~/.devcache/
├── config.json        settings + GitHub token
├── index.db           SQLite cache index
├── repos/             primary clones (one folder per repo)
└── worktrees/         git worktrees (worktrees/<repo>/<branch>)
```

### Design choices

- **SQLite over JSON** for the index: atomic writes, no full-file rewrites, and
  cheap queries as the cache grows.
- **Worktrees over re-cloning**: branches share one object store, so a second
  branch costs near-zero disk and clones in milliseconds.
- **Graceful degradation**: optional deps (`GitPython`, `requests`) and external
  tools (`gh`) are used when present but never required.
- **Single output layer** (`ui.py`): consistent colors/progress and easy theming.

---

## Configuration

`~/.devcache/config.json` (auto-created):

```json
{
  "github_user": "you",
  "github_token": "ghp_...",
  "default_editor": "code",
  "editors": {
    "code": "code",
    "nvim": "nvim",
    "cursor": "cursor"
  }
}
```

- `default_editor` — used when `--editor` isn't passed.
- `editors` — maps shorthand names to actual launch commands. Add your own.
- Set `DEVCACHE_HOME` to relocate all state (handy for testing or portable setups).

### Environment variables

| Variable | Purpose |
| --- | --- |
| `DEVCACHE_HOME` | Relocate all DevCache state (default: `~/.devcache`). |
| `DEVCACHE_GITHUB_TOKEN` | GitHub token (highest-priority env var). |
| `GITHUB_TOKEN` / `GH_TOKEN` | Fallback tokens, also picked up automatically. |

---

## Troubleshooting

**`dev` command not found after install**
The Python scripts directory isn't on your PATH. Either reopen your terminal, or
run via the module: `python -m devcache --help`. On Windows the scripts live in
`...\PythonXX\Scripts\`; on Linux/macOS in `~/.local/bin`.

**`Repo '<name>' not found locally or on GitHub`**
The name isn't cached and couldn't be resolved. Provide a URL
(`dev open <name> --url <git-url>`), use `owner/name` shorthand, or authenticate
first with `dev auth login`.

**`Editor '<x>' not found on PATH`**
The editor command isn't installed/visible. For VSCode, enable *Shell Command:
Install 'code' command in PATH* from the command palette, or pass another editor
with `--editor`, or edit the `editors` map in `config.json`.

**GitHub API rate limit exceeded**
Unauthenticated requests are rate-limited. Run `dev auth login` (or set
`GITHUB_TOKEN`) to raise the limit substantially.

**Clone is slow / hangs**
Large repos take time. Progress is shown live; for private repos make sure your
token or `gh` auth has the `repo` scope.

**Garbled characters on Windows**
DevCache reconfigures the console to UTF-8 automatically. If you still see odd
glyphs, use Windows Terminal (not the legacy console) or run `chcp 65001`.

---

## FAQ

**Why is the PyPI/distribution name `gitcache` but the command `dev`?**
The PyPI name `devcache` was already taken. The package import name and the
command stay the same; only the distribution name differs.

**Where are my repos stored?**
Under `~/.devcache/repos/`. Extra branches live in `~/.devcache/worktrees/`.
Nothing is stored in your current working directory.

**Does it work without `GitPython`, `requests`, or the `gh` CLI?**
Yes. It falls back to the system `git` (subprocess) and the stdlib `urllib`.
Those tools just make things nicer (progress bars, private-repo discovery).

**How do I move my cache to another drive?**
Set `DEVCACHE_HOME` to the new location (and move the existing folder there).

**Is my token safe?**
It's stored in `~/.devcache/config.json` with `chmod 600` where supported, and
`.devcache/` is git-ignored. You can also rely solely on `gh`/env vars.

---

## Contributing

```bash
git clone https://github.com/TurkerAlbayrak/gitcache.git
cd gitcache
pip install -e ".[full,dev]"
```

The codebase is intentionally small and modular (see **Architecture**). Each
module owns one concern, and `cli.py` is the only orchestration layer — a good
place to start reading. Issues and pull requests are welcome at
<https://github.com/TurkerAlbayrak/gitcache>.

### Building & publishing (maintainers)

```bash
python -m build                 # produces dist/*.whl and dist/*.tar.gz
python -m twine check dist/*    # validate metadata
python -m twine upload --repository testpypi dist/*   # test first
python -m twine upload dist/*                          # then real PyPI
```

Bump `version` in `pyproject.toml` for every release (PyPI rejects re-uploads
of an existing version).

---

## License

MIT — see [LICENSE](LICENSE).

