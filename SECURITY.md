# Security Policy

## Supported Versions

This project is in active pre-release development. Security updates are applied to the `main` branch only.

| Version       | Supported          |
| ------------- | ------------------ |
| `main` branch | :white_check_mark: |

Once versioned releases begin, this table will be updated to reflect which releases receive security patches.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, use [GitHub Security Advisories](https://github.com/CivicPulse/voter-api/security/advisories/new) to report vulnerabilities privately.

When reporting, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof of concept
- The affected component (API endpoint, CLI command, library, etc.)
- Any suggested fix, if you have one

## What to Expect

- **Acknowledgment**: We will acknowledge your report within 7 calendar days.
- **Assessment**: We will evaluate the severity and impact, and keep you informed of our progress.
- **Resolution**: Accepted vulnerabilities will be patched and disclosed responsibly. We will credit reporters unless they prefer to remain anonymous.
- **Declined reports**: If we determine the report is not a vulnerability, we will explain our reasoning.

## Scope

The following are in scope for security reports:

- The voter-api application (API endpoints, CLI, authentication, authorization)
- Dependencies with known vulnerabilities that affect this project
- Infrastructure configuration checked into this repository

The following are **out of scope**:

- Denial of service attacks
- Social engineering
- Vulnerabilities in third-party services not controlled by this project
