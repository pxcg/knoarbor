# knoarbor

[KnoArbor](https://github.com/pxcg/knoarbor) is an AI-native Wiki engine that compiles multi-source information into a traceable, maintainable knowledge network.

The main KnoArbor runtime is currently distributed as a Python project. This npm package reserves the public package name and CLI command names for future JavaScript/Node-based launchers.

For the current runtime, use the repository quickstart:

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
uv run knoar serve
```

After installation, this package exposes both command names:

- `knoar`
- `knoarbor`

