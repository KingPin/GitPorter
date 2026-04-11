"""Per-platform credential loading from environment variables."""
import os
import sys

from rich.console import Console

console = Console(stderr=True)

_REQUIRED: dict[str, list[str]] = {
    "github":    [],
    "gitea":     ["GITEA_URL"],
    "gitlab":    ["GITLAB_URL", "GITLAB_TOKEN"],
    "bitbucket": ["BITBUCKET_WORKSPACE", "BITBUCKET_USERNAME", "BITBUCKET_APP_PASSWORD"],
    "forgejo":   ["FORGEJO_URL", "FORGEJO_TOKEN"],
}

VALID_PLATFORMS = list(_REQUIRED.keys())


def load_platform_config(platform: str) -> dict:
    """Load and validate environment variables for the given platform.

    Returns a normalized dict with consistent keys.
    Raises SystemExit(1) if required vars are missing or platform is unknown.
    """
    if platform not in _REQUIRED:
        console.print(
            f"[red]Error:[/red] Unknown platform [bold]{platform!r}[/bold]. "
            f"Valid platforms: {', '.join(VALID_PLATFORMS)}"
        )
        sys.exit(1)

    missing = [var for var in _REQUIRED[platform] if not os.environ.get(var)]
    if missing:
        console.print(
            f"[red]Error:[/red] Missing required environment variable(s) for "
            f"[bold]{platform}[/bold]: {', '.join(missing)}"
        )
        sys.exit(1)

    if platform == "github":
        return {
            "url": "https://api.github.com",
            "token": os.environ.get("GITHUB_TOKEN", ""),
        }

    if platform == "gitea":
        token = os.environ.get("GITEA_TOKEN") or os.environ.get("ACCESS_TOKEN", "")
        if not token:
            console.print(
                "[red]Error:[/red] Missing required token for [bold]gitea[/bold]: "
                "set GITEA_TOKEN or ACCESS_TOKEN"
            )
            sys.exit(1)
        return {
            "url": os.environ.get("GITEA_URL", "").rstrip("/"),
            "token": token,
        }

    if platform == "gitlab":
        return {
            "url": os.environ.get("GITLAB_URL", "").rstrip("/"),
            "token": os.environ.get("GITLAB_TOKEN", ""),
        }

    if platform == "bitbucket":
        return {
            "workspace":    os.environ.get("BITBUCKET_WORKSPACE", ""),
            "username":     os.environ.get("BITBUCKET_USERNAME", ""),
            "app_password": os.environ.get("BITBUCKET_APP_PASSWORD", ""),
        }

    if platform == "forgejo":
        return {
            "url":   os.environ.get("FORGEJO_URL", "").rstrip("/"),
            "token": os.environ.get("FORGEJO_TOKEN", ""),
        }

    # unreachable — kept for type-checker completeness
    raise AssertionError(f"Unhandled platform: {platform}")
