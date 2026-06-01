## Summary

Describe the change and the user/system problem it solves.

## Type

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation
- [ ] Test

## Boundary Check

- [ ] Connectors only read/normalize sources.
- [ ] Pipelines own orchestration.
- [ ] Semantic steps use explicit prompt/schema contracts.
- [ ] Vault writes go through storage/write or operation pipelines.
- [ ] No hidden fallback behavior was added.

## Privacy Check

- [ ] No `.env`, API key, private path, raw source, runtime wiki, or local workflow credential is committed.
- [ ] Logs and examples are redacted.

## Validation

Commands run:

```text
uv run --extra dev python -m unittest discover tests
cd web && npm run build
uv build
```
