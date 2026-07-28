# Security Policy

## Reporting a vulnerability

Please do not open a public issue, discussion, or pull request for a suspected vulnerability.

Use the repository's **Security** tab and select **Report a vulnerability** to send the maintainers a private report. Include:

- the affected URL, file, or workflow;
- clear reproduction steps;
- the expected and observed impact;
- any suggested remediation;
- whether the issue is already public or actively exploited.

Do not include real API keys, access tokens, private user data, or destructive proof-of-concept payloads. Use harmless placeholders and the minimum access needed to demonstrate the issue.

The maintainers will acknowledge valid reports, investigate impact, prepare a fix, and coordinate disclosure. Please allow a reasonable remediation window before publishing details.

## Supported versions

The live site and the latest commit on `main` are supported. Old deployments, forks, and historical commits are not maintained.

## Security boundaries

The public site is intentionally static and does not accept accounts, uploads, payments, or user-submitted content. Reports about browser injection, deployment exposure, data-pipeline integrity, credential handling, GitHub Actions, or the published dataset are in scope.
