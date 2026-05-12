# Security Policy

This public repository should contain only code, schema, validation tooling, and
public documentation. It must not contain source exports, generated database
files, production secrets, copied restricted content, or personal machine paths.

## Reporting

If you find a real secret, token, personal data leak, copied restricted artifact,
or misleading official-affiliation wording, use the repository host's security
advisory flow if available. Otherwise, contact the maintainer before creating a
public issue.

## Supported Checks

Run these before publishing:

```bash
nix run path:$PWD#validate-public
```

Example placeholders may exist in code comments or documentation. Real secrets must not be committed.
