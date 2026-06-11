"""Terminal UX helpers built on top of ``rich``.

Centralises all output so the rest of the codebase never prints raw text. This
keeps colors, tables, progress bars, and prompts consistent and themable.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Iterable, Iterator, List, Optional

# On Windows the console often defaults to a legacy codepage (cp1252) that can't
# encode the Unicode glyphs rich uses. Reconfigure to UTF-8 and never hard-fail
# on an un-encodable character.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

console = Console()
err_console = Console(stderr=True)


# ----------------------------------------------------------------------
# Simple messages
# ----------------------------------------------------------------------
def success(message: str) -> None:
    console.print(f"[bold green]\u2713[/] {message}")


def info(message: str) -> None:
    console.print(f"[bold cyan]\u2139[/] {message}")


def warn(message: str) -> None:
    console.print(f"[bold yellow]\u26a0[/] {message}")


def error(message: str) -> None:
    err_console.print(f"[bold red]\u2717[/] {message}")


def hint(message: str) -> None:
    console.print(f"[dim]\u2192 {message}[/]")


def banner() -> None:
    console.print(
        Panel.fit(
            Text("DevCache", style="bold magenta")
            + Text("  \u2022  local GitHub repository manager", style="dim"),
            border_style="magenta",
        )
    )


# ----------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------
def ask(prompt: str, default: Optional[str] = None, password: bool = False) -> str:
    return Prompt.ask(prompt, default=default, password=password, console=console)


def confirm(prompt: str, default: bool = False) -> bool:
    return Confirm.ask(prompt, default=default, console=console)


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------
def repo_table(rows: Iterable, title: str = "Cached repositories") -> None:
    table = Table(title=title, title_style="bold magenta", header_style="bold cyan")
    table.add_column("Repo", style="bold")
    table.add_column("Branches", justify="right")
    table.add_column("Last opened", style="green")
    table.add_column("Origin", style="dim", overflow="fold")

    rows = list(rows)
    if not rows:
        console.print("[dim]No repositories cached yet. Try:[/] [bold]dev open <repo>[/]")
        return

    for name, branch_count, last_opened, origin in rows:
        table.add_row(name, str(branch_count), last_opened, origin or "-")
    console.print(table)


def worktree_table(repo_name: str, rows: Iterable) -> None:
    table = Table(
        title=f"Worktrees for {repo_name}",
        title_style="bold magenta",
        header_style="bold cyan",
    )
    table.add_column("Branch", style="bold")
    table.add_column("Path", style="dim", overflow="fold")
    rows = list(rows)
    if not rows:
        console.print("[dim]No additional worktrees.[/]")
        return
    for branch, path in rows:
        table.add_row(branch, path)
    console.print(table)


def search_results(results: List) -> None:
    if not results:
        console.print("[dim]No matches.[/]")
        return
    table = Table(header_style="bold cyan", box=None)
    table.add_column("Repo", style="bold")
    table.add_column("Last opened", style="green")
    for repo in results:
        table.add_row(repo.name, repo.last_opened_str)
    console.print(table)


# ----------------------------------------------------------------------
# Progress
# ----------------------------------------------------------------------
@contextmanager
def clone_progress(description: str) -> Iterator["Progress"]:
    """A progress bar suited to git clone/fetch operations."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        DownloadColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    with progress:
        yield progress


@contextmanager
def spinner(description: str) -> Iterator[None]:
    """A lightweight spinner for indeterminate operations."""
    with console.status(f"[bold blue]{description}", spinner="dots"):
        yield
