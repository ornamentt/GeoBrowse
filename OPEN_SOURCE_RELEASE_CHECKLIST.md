# Open Source Release Checklist

Use this sanitized repository as the public release source:

```bash
/workspace/gengxinyu/cognitive_kernel_GAIA_sanitized
```

Do not publish the original extracted repository because its Git history contains previously exposed credentials and browser cookies.

## Required External Credential Rotation

Removing secrets from this repository does not revoke them. Rotate or delete every credential below in the corresponding provider console before publishing:

- Browserless: revoke the exposed Browserless token and create a new token if needed.
- Azure OpenAI/OpenAI: revoke exposed API keys, rotate deployment credentials, and review usage logs.
- Tencent Cloud COS: disable the exposed secret ID/secret key pair, create a least-privilege replacement if the COS image workflow is still needed, and review bucket access logs.
- Google Search/Google CSE/SerpAPI: revoke the exposed API keys, create scoped replacements, and restrict new keys by API and referrer/IP where possible.
- ModelScope or other evaluation provider: revoke the exposed evaluation API key.
- Git hosting: revoke any token embedded in old remote URLs and audit recent access.
- Browser sessions: invalidate exposed Google/YouTube sessions by signing out of all sessions and rotating passwords or session credentials if required by policy.

## Local Release Gates

Run from the sanitized repository:

```bash
./scripts/verify_open_source_ready.sh
```

Expected result:

- Shell entry scripts parse successfully.
- Key Python entry points compile.
- No known exposed credentials or internal paths are present in the current tree or new Git history.
- `gitleaks detect` reports no leaks.
- Generated artifacts such as `__pycache__`, `node_modules`, screenshots, and `.pyc` files are not tracked.

## Publishing Steps

1. Confirm all external credentials above have been revoked or rotated.
2. Run `./scripts/verify_open_source_ready.sh`.
3. Add the public Git remote to the sanitized repository, not the original repository.
4. Push only the sanitized history.
5. After publishing, run the hosting provider's secret scanning and review the result.
