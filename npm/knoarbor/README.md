# knoarbor

[KnoArbor](https://github.com/pxcg/knoarbor) is an AI-native Wiki engine that compiles multi-source information into a traceable, maintainable knowledge network.

The main KnoArbor runtime is currently distributed as a Python project. This npm package provides a lightweight launcher that forwards commands to a local KnoArbor checkout.

Install the runtime first:

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
uv run knoar first-run
uv run knoar serve
```

Then run npm commands from inside that repository:

```bash
npx knoarbor doctor
npx knoarbor serve
npx knoarbor ingest --connector markdown --write
```

If you run the launcher from another directory, set:

```bash
export KNOARBOR_HOME=/path/to/knoarbor
```

When installed as a package dependency or global package, it exposes both
command names:

- `knoar`
- `knoarbor`
