# Security Policy

## Supported Versions

| Version    | Supported          |
| ---------- | ------------------ |
| 2026Q3.1   | :white_check_mark: |

We support the latest release only. The check pack version is in `readiness/checks/shopify-v1.yaml`.

## Reporting a Vulnerability

Email **sergeigodev@gmail.com** with:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment

We will acknowledge within 48 hours and aim to patch critical issues within 7 days.

**Do not open public issues for security vulnerabilities.**

## Security Measures

This scanner includes 5 security checks (RDY-016, RDY-042–045) that detect:

- Hidden prompt injection in page content
- Prompt injection in user-generated content (reviews, Q&A)
- Cart API rate limiting gaps
- Missing checkout bot challenges
- Exposed admin/API paths

The codebase is scanned by CodeQL on every push.
