# Contributing

This public companion repository is intentionally data-free. Contributions should preserve that boundary.

## Development Setup

```bash
nix develop path:$PWD
nix run path:$PWD#validate-public
```

## Contribution Rules

- Do not add source ZIPs, extracted artifacts, generated databases, local logs, or local maintenance reports.
- Do not add real API keys, credentials, personal data, or machine-specific paths.
- Keep OpenAI references descriptive and avoid language that implies official affiliation.
- Keep build code and schema changes compatible with the documented artifact layout.
- If a change requires generated or restricted data to test, keep only the public-safe code here.

## Pull Request Checklist

- `nix flake check path:$PWD`
- `nix run path:$PWD#validate-public`
- No excluded paths from `PUBLIC_RELEASE_BOUNDARY.md`
- No real secrets or personal paths
- Public-facing wording still says the project is unofficial and fan-made
