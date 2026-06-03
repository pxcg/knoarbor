#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const args = process.argv.slice(2);
const root = resolveRuntimeRoot();

if (!root) {
  printInstallHelp();
  process.exit(args.includes("--help") || args.includes("-h") ? 0 : 1);
}

const result = spawnSync("uv", ["run", "knoar", ...args], {
  cwd: root,
  stdio: "inherit",
  shell: process.platform === "win32",
});

if (result.error) {
  console.error(`KnoArbor launcher failed: ${result.error.message}`);
  console.error("Install uv first: https://docs.astral.sh/uv/");
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);

function resolveRuntimeRoot() {
  const explicit = process.env.KNOARBOR_HOME;
  if (explicit && isKnoArborRoot(explicit)) {
    return path.resolve(explicit);
  }
  let current = process.cwd();
  while (true) {
    if (isKnoArborRoot(current)) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

function isKnoArborRoot(candidate) {
  const pyproject = path.join(candidate, "pyproject.toml");
  if (!fs.existsSync(pyproject)) {
    return false;
  }
  const text = fs.readFileSync(pyproject, "utf8");
  return /\bname\s*=\s*["']knoarbor["']/.test(text);
}

function printInstallHelp() {
  console.log(`KnoArbor npm launcher

This package forwards commands to a local KnoArbor Python runtime.

Install the runtime:

  git clone https://github.com/pxcg/knoarbor.git
  cd knoarbor
  uv sync
  uv run knoar first-run
  uv run knoar serve

Then run npm commands from inside that repository, or set:

  export KNOARBOR_HOME=/path/to/knoarbor

Examples:

  knoarbor first-run
  knoarbor serve
  knoar ingest --connector markdown --write
`);
}
