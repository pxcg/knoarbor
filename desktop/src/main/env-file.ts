import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { dirname } from "node:path";

const ENV_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function readDesktopEnvFile(envPath: string): Record<string, string> {
  if (!existsSync(envPath)) return {};
  const values: Record<string, string> = {};
  const content = readFileSync(envPath, "utf-8");
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const index = trimmed.indexOf("=");
    if (index <= 0) continue;
    const key = trimmed.slice(0, index).trim();
    if (!ENV_NAME_PATTERN.test(key)) continue;
    values[key] = parseEnvValue(trimmed.slice(index + 1).trim());
  }
  return values;
}

export function writeDesktopEnvSecrets(
  envPath: string,
  secrets: Record<string, string>,
): string[] {
  const normalized = normalizeSecrets(secrets);
  const names = Object.keys(normalized);
  if (!names.length) return [];

  const existingLines = existsSync(envPath)
    ? readFileSync(envPath, "utf-8").split(/\r?\n/)
    : [];
  const secretNames = new Set(names);
  const nextLines = existingLines.filter((line) => {
    const trimmed = line.trim();
    const index = trimmed.indexOf("=");
    if (index <= 0 || trimmed.startsWith("#")) return true;
    return !secretNames.has(trimmed.slice(0, index).trim());
  });

  for (const name of names) {
    nextLines.push(`${name}=${JSON.stringify(normalized[name])}`);
  }

  mkdirSync(dirname(envPath), { recursive: true });
  writeFileSync(envPath, `${nextLines.filter((line, index, lines) => line || index < lines.length - 1).join("\n")}\n`, {
    encoding: "utf-8",
    mode: 0o600,
  });
  try {
    chmodSync(envPath, 0o600);
  } catch {
    // chmod can fail on some Windows filesystems; the file is still written.
  }
  return names;
}

function normalizeSecrets(secrets: Record<string, string>): Record<string, string> {
  const normalized: Record<string, string> = {};
  for (const [rawName, rawValue] of Object.entries(secrets)) {
    const name = rawName.trim();
    const value = String(rawValue ?? "").trim();
    if (!name || !value) continue;
    if (!ENV_NAME_PATTERN.test(name)) {
      throw new Error(`Invalid environment variable name: ${name}`);
    }
    normalized[name] = value;
  }
  return normalized;
}

function parseEnvValue(value: string): string {
  if (!value) return "";
  if (
    (value.startsWith("\"") && value.endsWith("\"")) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    try {
      return JSON.parse(value);
    } catch {
      return value.slice(1, -1);
    }
  }
  return value;
}
