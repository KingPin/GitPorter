# Security Policy

## Supported Versions

Only the latest commit on `master` is supported. No backports are made to older versions.

## Scope

Issues in scope:

- Credential or token exposure (e.g. tokens leaked in logs, error messages, or process lists)
- Command injection via repository names or user-supplied inputs passed to subprocesses
- Privilege escalation through environment variable handling
- Unintended network requests to attacker-controlled hosts (SSRF)

Out of scope:

- Rate limiting or quotas enforced by third-party platforms (GitHub, GitLab, etc.)
- Behaviour that requires the attacker to already control the environment variables or Docker runtime
- Issues in third-party dependencies — please report those upstream

## Reporting a Vulnerability

Use [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability):
**Security tab → "Report a vulnerability"**

Please include:

- A clear description of the issue
- Steps to reproduce or a proof-of-concept
- The impact you believe it has

## Response Timeline

| Event | Target |
|-------|--------|
| Acknowledgement | 7 days |
| Status update | 14 days |
| Fix or workaround | 30 days (best effort) |

This is a solo-maintained project. There is no bug bounty program.
