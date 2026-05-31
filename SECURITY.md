# Security Policy

KnoArbor is designed to process personal notes, AI chat logs, and local documents. Treat generated wiki vaults and raw sources as private runtime data unless you intentionally publish them.

## Do Not Commit

Do not commit:

- `.env` or any file containing API keys.
- `config.yaml` if it contains private local paths or connector settings.
- `wiki/` runtime vault contents.
- `wiki/raw/` source exports, chat logs, PDFs, Office documents, screenshots, or company documents.
- Obsidian workspace state or local editor caches.

The repository `.gitignore` excludes these by default, but review changes before pushing.

## Model Provider Secrets

Model provider keys should be stored in environment variables referenced by `config.yaml`, for example:

```yaml
models:
  providers:
    deepseek:
      api_key_env: DEEPSEEK_API_KEY
```

Do not paste keys into prompts, wiki pages, source documents, examples, issue reports, or screenshots.

## Data Sent to Models

Ingest and lint semantic workflows send selected source content and wiki page context to the configured model provider. Before using cloud models with private or company data:

- Confirm the provider and endpoint in `config.yaml`.
- Review connector roots and vault paths.
- Enable privacy redaction where appropriate.
- Prefer local OpenAI-compatible servers for sensitive data.

## Reporting Security Issues

Please report security issues privately through GitHub Security Advisories when available:

```text
https://github.com/pxcg/knoarbor/security/advisories
```

If private advisories are unavailable, open a minimal public issue asking for a private contact channel. Do not include secrets, private source files, local vault contents, screenshots with API keys, or company data in public issues.
