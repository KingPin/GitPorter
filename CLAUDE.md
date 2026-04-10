# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repo contains two Bash scripts for managing GitHub → Gitea migrations:

- **`github-mirror-2-gitea.sh`** — mirrors GitHub repos to a Gitea instance (org, user, starred, or single repo)
- **`delete_gitea_org`** — deletes a Gitea organization and all its repositories

## Required Environment Variables

Both scripts require:
```bash
export ACCESS_TOKEN=<gitea-token>
export GITEA_URL=http://gitea:3000   # no trailing slash
```

`github-mirror-2-gitea.sh` also uses `GITHUB_TOKEN` for authenticated GitHub API requests.

## Dependencies

Both scripts require `curl` and `jq` to be installed.

## Usage

### Mirror script modes

```bash
# Mirror a GitHub org
./github-mirror-2-gitea.sh -m org -o <org> -v <public|private>

# Mirror all repos of a GitHub user (to user account)
./github-mirror-2-gitea.sh -m user -u <github_user>

# Mirror all repos of a GitHub user (to a Gitea org)
./github-mirror-2-gitea.sh -m user -u <github_user> -o <gitea_org> -v <public|private>

# Mirror starred repos of a user into a Gitea org
./github-mirror-2-gitea.sh -m star -u <github_user> -o <gitea_org>

# Mirror a single repo
./github-mirror-2-gitea.sh -m repo -r <github_repo_url> -u <github_user>
```

### Delete org script

```bash
# Dry run (lists what would be deleted)
./delete_gitea_org -o <org> --dry-run

# Interactive delete (prompts for confirmation)
./delete_gitea_org -o <org>

# Force delete (no prompt — CI/CD use only)
./delete_gitea_org -o <org> --force
```

## Key Behaviors

- **Rate limiting**: `github-mirror-2-gitea.sh` uses exponential backoff on GitHub 403/429 responses, with configurable pacing (`GITHUB_API_DELAY`, `GITEA_API_DELAY` at top of file).
- **Gitea 422 error**: Means `github.com` is not in the `[migrations] ALLOWED_DOMAINS` list in Gitea's `app.ini`.
- **Repo already exists**: HTTP 409 from Gitea is treated as a skip (not an error).
- **delete_gitea_org pagination**: Fetches all repos in pages of 50 before deletion to avoid missing repos.
