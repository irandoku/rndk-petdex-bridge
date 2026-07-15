# Security Policy

## Scope

`rndk-petdex-bridge` is a local loopback bridge between Hermes Agent and the Petdex Desktop sidecar. It does not operate a network service and does not store credentials.

## Sensitive data

The plugin reads `~/.petdex/runtime/update-token` only when sending a state update. The token is transmitted to `127.0.0.1:7777` in the `X-Petdex-Update-Token` header and is never returned by `/rndk-petdex status`.

Do not include the token file or its contents in issue reports.

## Reporting

Please report suspected vulnerabilities through GitHub's private vulnerability reporting feature for this repository. Avoid opening a public issue when a report contains security-sensitive details.
