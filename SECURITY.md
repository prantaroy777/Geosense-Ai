# Security and deployment

This alpha is a local research application. Bind Streamlit to 127.0.0.1.
Do not expose it directly to the internet: it has no authentication, tenant
isolation, job queue or deployment-level memory/CPU controls. Use trusted data
and keep Python and native GIS libraries updated. Archive quotas bound input
sizes, but complex geometries and rendering can still consume substantial RAM.

Never commit credentials, personal study data, generated reports or run bundles.
The source release builder uses an explicit file allowlist. Review the archive
before publishing. Checksums detect accidental changes, not malicious alteration
by someone who can also rewrite the manifest.

For sensitive vulnerabilities, use the repository's private vulnerability
reporting facility when enabled; otherwise contact its maintainer privately.
Do not put credentials, private files or working exploits in public issues.
Only the latest alpha is maintained. No response-time guarantee is offered.

## Known dependency issue (2026-10-22)

The tested Python 3.10 environment resolves Streamlit 1.65.0 and Pillow 12.3.0.
`pip-audit` reports 35 Pillow advisories with fixes in 13.0.0. Streamlit's declared
constraint is `pillow<13`; Pillow 13 also requires Python >=3.11. These findings
are not suppressed. Upgrading Python alone does not resolve the Streamlit
constraint. Reassess after a compatible upstream update, then rerun tests and
the audit. This release is not approved for public hosting or hostile uploads.
