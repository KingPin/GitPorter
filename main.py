#!/usr/bin/env python3
import argparse
import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from github2gitea.adapters import get_adapter
from github2gitea.config import load_platform_config
from github2gitea.core.migrator import Migrator

console = Console()


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def print_summary(results: list) -> None:
    migrated = sum(1 for r in results if r.status == "MIGRATED")
    skipped  = sum(1 for r in results if r.status == "SKIPPED")
    failed   = sum(1 for r in results if r.status == "FAILED")

    table = Table(title="Migration Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("[green]Migrated[/green]", str(migrated))
    table.add_row("[yellow]Skipped[/yellow]",  str(skipped))
    table.add_row("[red]Failed[/red]",    str(failed))
    console.print(table)

    failures = [r for r in results if r.status == "FAILED"]
    if failures:
        console.print("\n[red]Failed repos:[/red]")
        for r in failures:
            console.print(f"  • {r.repo_name} — {r.reason}")


def _validate_migrate_args(args: argparse.Namespace) -> None:
    """Fail fast with a clear message when required per-mode flags are missing."""
    if args.mode == "org" and not args.org:
        console.print("[red]Error:[/red] --mode org requires --org"); sys.exit(1)
    if args.mode == "user" and not args.user:
        console.print("[red]Error:[/red] --mode user requires --user"); sys.exit(1)
    if args.mode == "star" and (not args.user or not args.org):
        console.print("[red]Error:[/red] --mode star requires --user and --org"); sys.exit(1)
    if args.mode == "repo" and (not args.repo or not args.user):
        console.print("[red]Error:[/red] --mode repo requires --repo and --user"); sys.exit(1)
    if args.source == "bitbucket" and args.mode == "star":
        console.print("[red]Error:[/red] Bitbucket does not support --mode star"); sys.exit(1)


def cmd_migrate(args: argparse.Namespace) -> None:
    _validate_migrate_args(args)
    setup_logging(args.verbose)

    source_cfg = load_platform_config(args.source)
    dest_cfg   = load_platform_config(args.dest)
    source = get_adapter(args.source, source_cfg)
    dest   = get_adapter(args.dest,   dest_cfg)

    if args.dry_run:
        console.print("[bold yellow][DRY RUN][/bold yellow] No repos will be migrated.")

    ignore_names = [s.strip() for s in args.ignore_repos.split(",") if s.strip()] if args.ignore_repos else None
    migrator = Migrator(
        source=source, dest=dest, dry_run=args.dry_run,
        name_pattern=args.filter_name, language=args.filter_language,
        topic=args.filter_topic, dest_org=args.org,
        ignore_names=ignore_names,
        enable_lfs=args.lfs,
        cleanup_action=args.cleanup_action,
    )
    results = migrator.run(mode=args.mode, user=args.user, org=args.org, repo_url=args.repo)
    print_summary(results)
    if any(r.status == "FAILED" for r in results):
        sys.exit(1)


def cmd_delete(args: argparse.Namespace) -> None:
    setup_logging(args.verbose)
    dest_cfg = load_platform_config(args.dest)
    adapter  = get_adapter(args.dest, dest_cfg)
    if not hasattr(adapter, "delete_org"):
        console.print(f"[red]Error:[/red] Platform {args.dest!r} does not support delete_org.")
        sys.exit(1)
    adapter.delete_org(org=args.org, force=args.force, dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github2gitea",
        description="Mirror repos between Git platforms.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    # migrate subcommand
    m = sub.add_parser("migrate", help="Mirror repos from source to destination")
    m.add_argument("--source",  required=True,
                   choices=["github", "gitea", "gitlab", "bitbucket", "forgejo"])
    m.add_argument("--dest",    required=True,
                   choices=["github", "gitea", "gitlab", "forgejo"])
    m.add_argument("--mode",    required=True, choices=["org", "user", "star", "repo"])
    m.add_argument("--org",  "-o")
    m.add_argument("--user", "-u")
    m.add_argument("--visibility", choices=["public", "private"], default="public")
    m.add_argument("--repo", "-r")
    m.add_argument("--filter-name",     dest="filter_name")
    m.add_argument("--filter-language", dest="filter_language")
    m.add_argument("--filter-topic",    dest="filter_topic")
    m.add_argument("--ignore-repos",    dest="ignore_repos")
    m.add_argument("--dry-run", action="store_true")
    m.add_argument("--lfs", action="store_true", help="Enable Git LFS support for mirrored repos")
    m.add_argument("--cleanup-action", dest="cleanup_action", choices=["archive", "delete"])
    m.set_defaults(func=cmd_migrate)

    # delete subcommand
    d = sub.add_parser("delete", help="Delete a platform org and all its repos")
    d.add_argument("--dest", required=True, choices=["gitea", "forgejo"])
    d.add_argument("--org", "-o", required=True)
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--force",   action="store_true")
    d.set_defaults(func=cmd_delete)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
