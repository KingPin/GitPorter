# Contributing

## Development Setup

All code runs inside Docker — no local Python install needed.

```bash
git clone <repo>
cd gitporter
docker compose build
```

Run the test suite:

```bash
docker compose run --rm test
```

Run a specific test file:

```bash
docker compose run --rm test tests/adapters/test_gitea.py -v
```

## Making Changes

1. Fork the repo and create a branch from `master`
2. Make your changes
3. Add or update tests for any changed behaviour
4. Run `docker compose run --rm test` — all tests must pass
5. Open a pull request against `master`

Keep PRs focused. One logical change per PR is easier to review and less likely to be stalled.

## Adding a New Platform Adapter

See the [Adding a New Adapter](CLAUDE.md#adding-a-new-adapter) section in `CLAUDE.md` for the step-by-step checklist. The short version:

1. Create `gitporter/adapters/<platform>.py`, subclass `BaseAdapter`
2. Implement `list_repos`, `create_mirror`, `repo_exists`
3. Add credentials to `config.py`
4. Register in `adapters/__init__.py`
5. Add to `choices=` in `main.py`
6. Add tests in `tests/adapters/`

## Code Style

- Standard Python 3.11+, no formatter enforced
- Type annotations on all public methods
- No dependencies beyond what is in `requirements.txt` unless justified in the PR

## Reporting Bugs

Open a GitHub issue. Include the command you ran, the error output, and the platform combination (source → dest).

For security issues, see [SECURITY.md](SECURITY.md).
