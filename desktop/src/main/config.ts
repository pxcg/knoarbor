import { app } from "electron";
import {
  cpSync,
  existsSync,
  mkdirSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_HOST = "127.0.0.1";
const PRODUCT_APP_DATA_DIR = "KnoArbor";
const LEGACY_APP_DATA_PARTS = ["@knoarbor", "desktop"];

export type DesktopAppServerConfig =
  | {
      mode: "external";
      url: string;
    }
  | {
      appDataRoot: string;
      configPath: string;
      host: string;
      mode: "managed";
      port: number;
      serviceCommand: string;
      serviceArgs: string[];
      serviceCwd: string;
      webAssetsRoot: string;
    };

export type DesktopAppConfig = {
  appServer: DesktopAppServerConfig;
  appUserModelId: string;
};

export function resolveDesktopAppConfig(): DesktopAppConfig {
  return {
    appServer: resolveAppServerConfig(),
    appUserModelId: "com.knoarbor.desktop",
  };
}

export function configureDesktopUserDataPath(): string {
  const override = process.env.KNOARBOR_DESKTOP_APP_DATA_ROOT?.trim();
  if (override) {
    app.setPath("userData", override);
    return override;
  }

  const appDataRoot = app.getPath("appData");
  const targetRoot = join(appDataRoot, PRODUCT_APP_DATA_DIR);
  const legacyRoot = join(appDataRoot, ...LEGACY_APP_DATA_PARTS);
  migrateLegacyUserData(legacyRoot, targetRoot);
  app.setPath("userData", targetRoot);
  return targetRoot;
}

function resolveAppServerConfig(): DesktopAppServerConfig {
  const externalUrl = process.env.KNOARBOR_DESKTOP_APP_SERVER_URL?.trim();
  if (externalUrl) {
    return { mode: "external", url: externalUrl };
  }

  const appDataRoot =
    process.env.KNOARBOR_DESKTOP_APP_DATA_ROOT?.trim() || app.getPath("userData");
  const configPath = resolveConfigPath(
    process.env.KNOARBOR_CONFIG_PATH?.trim(),
    appDataRoot,
  );
  const webAssetsRoot = app.isPackaged
    ? join(process.resourcesPath, "web")
    : join(findDesktopRoot(), "resources", "web");

  return {
    appDataRoot,
    configPath,
    host: process.env.KNOARBOR_DESKTOP_APP_SERVER_HOST ?? DEFAULT_HOST,
    mode: "managed",
    port: readPort(process.env.KNOARBOR_DESKTOP_APP_SERVER_PORT),
    serviceArgs: readServiceArgs(app.isPackaged),
    serviceCommand: resolveServiceCommand(app.isPackaged),
    serviceCwd:
      process.env.KNOARBOR_DESKTOP_SERVICE_CWD?.trim() ||
      (app.isPackaged ? appDataRoot : findRepoRootFromDesktopRoot()),
    webAssetsRoot,
  };
}

export function ensureDesktopBootstrapConfig(config: DesktopAppServerConfig): void {
  if (config.mode !== "managed") return;
  const defaultVaultRoot = join(config.appDataRoot, "vaults", "default");
  createDesktopVaultLayout(defaultVaultRoot);
  mkdirSync(dirname(config.configPath), { recursive: true });
  if (existsSync(config.configPath)) return;
  writeFileSync(
    config.configPath,
    desktopDefaultConfigYaml({
      host: config.host,
      port: config.port || 0,
      vaultPath: defaultVaultRoot,
    }),
    "utf-8",
  );
}

function createDesktopVaultLayout(vaultRoot: string): void {
  const directories = [
    "raw/inbox/documents",
    "raw/inbox/media",
    "raw/inbox/notes",
    "raw/normalized/chats",
    "raw/normalized/excerpts",
    "raw/normalized/markdown",
    "raw/assets/images",
    "raw/assets/media",
    "raw/assets/pages",
    "raw/assets/tables",
    "raw/sidecars/documents",
    "raw/sidecars/sources",
    "wiki/pages",
    "wiki/sources",
    "maintenance/reports/ingest",
    "maintenance/reports/lint",
    "maintenance/reports/query",
    "maintenance/reports/run-failure",
    "maintenance/archives",
    ".knoarbor/index",
    ".knoarbor/ledgers",
    ".knoarbor/checkpoints",
    ".knoarbor/runs",
    ".knoarbor/queue",
    ".knoarbor/locks",
    ".knoarbor/logs",
    ".knoarbor/chat/sessions",
  ];
  for (const directory of directories) {
    mkdirSync(join(vaultRoot, directory), { recursive: true });
  }
}

function desktopDefaultConfigYaml(input: {
  host: string;
  port: number;
  vaultPath: string;
}): string {
  const port = input.port > 0 ? input.port : 8000;
  const vaultPath = pathRelativeToConfigDir(input.vaultPath);
  const vaultRelative = (relativePath: string): string => `${vaultPath}/${relativePath}`;
  return `# KnoArbor Desktop local configuration.
# Model providers use direct API key fields in the settings page.

project:
  name: My Knowledge Base
  host_project_root: .

config_version: 1

vaults:
  default: default
  profiles:
    default:
      name: My Knowledge Base
      path: ${quoteYamlString(vaultPath)}

vault:
  path: ${quoteYamlString(vaultPath)}

server:
  host: ${quoteYamlString(input.host)}
  port: ${port}

models:
  default_provider: deepseek
  default_max_tokens: 30000
  request_timeout_seconds: 600
  retry:
    enabled: true
    max_attempts: 2
    backoff_seconds: 2
    retry_on_invalid_output: true
  providers:
    deepseek:
      adapter: openai_compatible
      base_url: https://api.deepseek.com
      api_key:
      model: deepseek-v4-flash
      json_mode: true
      tls_ca_file:
      context_window:
      max_output_tokens:
      extra_body: {}

document_processing:
  mineru:
    enabled: false
    endpoint: http://127.0.0.1:18000/file_parse
    input_dir: ${quoteYamlString(vaultRelative("raw/inbox/documents"))}
    output_dir: ${quoteYamlString(vaultRelative("raw/normalized/markdown"))}
    recursive: true
    patterns:
      - "*.pdf"
      - "*.docx"
      - "*.pptx"
    mode: auto
    timeout_seconds: 600
    file_field: files
    output_dir_field:
    mode_field: parse_method
    response_markdown_field: markdown
    response_path_field:
    headers: {}
    extra_fields:
      backend: pipeline
      lang_list: ch
      formula_enable: true
      table_enable: true
      start_page_id: 0
      end_page_id: 99999
      return_md: true
      return_middle_json: false
      return_model_output: false
      return_content_list: false
      return_images: true
      response_format_zip: false

connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - ${quoteYamlString(vaultRelative("raw/inbox/notes"))}
        - ${quoteYamlString(vaultRelative("raw/normalized/markdown"))}
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/notes"))}
      preserve_relative_paths: true
  codex:
    enabled: false
    settings:
      sessions_dir: ~/.codex/sessions
      pattern: "rollout-*.jsonl"
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/normalized/chats"))}
  hermes:
    enabled: false
    settings:
      sessions_dir: ~/.hermes/sessions
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/normalized/chats"))}
  openclaw:
    enabled: false
    settings:
      sessions_dir: ~/.openclaw/agents/main/sessions
      pattern: "*.jsonl"
      recursive: false
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/normalized/chats"))}
  claude_code:
    enabled: false
    settings:
      sessions_dir: ~/.claude/projects
      pattern: "*.jsonl"
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/normalized/chats"))}
  generic_chat:
    enabled: false
    settings:
      roots: []
      patterns:
        - "*.jsonl"
        - "*.sqlite"
        - "*.db"
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/normalized/chats"))}

query:
  mode: balanced
  max_results: 6
  max_pages_to_read: 10
  max_excerpts_per_page: 3
  max_chars_per_excerpt: 800
  max_context_chars: 8000
  page_dirs: []
  include_related: true

memory:
  enabled: true
  auto_write_explicit_low_risk: true
  max_recalled_records: 12

chat:
  auto_ingest:
    enabled: false
    trigger: on_session_close
    min_user_turns: 2
    write: true
    write_report: true
    append_ledger: true

ingest:
  candidate_limit: 8
  materialized_page_limit: 8
  max_chars_per_materialized_page: 6000
  auto_scoped_lint: true
  auto_apply_safe_lint_fixes: true
  segmentation:
    enabled: true
    max_chars_per_segment: 18000
    soft_chars_per_segment: 12000
    max_segments_per_source: 20
    min_segment_chars: 1000
  recovery:
    enabled: true
    execution_ledger_path: .knoarbor/ledgers/ingest_execution.jsonl
  concurrency:
    max_concurrent_sources: 1

lint:
  default_scope: latest-ingest
  scoped_include_related: true
  include_neighbors: true
  include_global_checks: true

privacy:
  redaction_enabled: true
  redact_emails: true
  redact_phone_numbers: true
  redact_api_keys: true
  redact_private_keys: true
  redact_platform_ids: true
  redact_local_paths: true
  redact_source_paths_in_pages: true
  redact_private_ips: false
  custom_terms: []
`;
}

function migrateLegacyUserData(legacyRoot: string, targetRoot: string): void {
  if (!existsSync(legacyRoot) || legacyRoot === targetRoot) return;
  if (!existsSync(targetRoot)) {
    mkdirSync(dirname(targetRoot), { recursive: true });
    try {
      renameSync(legacyRoot, targetRoot);
      return;
    } catch {
      mkdirSync(targetRoot, { recursive: true });
    }
  }

  for (const entry of [
    "config.yaml",
    "vaults",
    ".knoarbor",
    "state",
    "logs",
  ]) {
    const source = join(legacyRoot, entry);
    const target = join(targetRoot, entry);
    if (!existsSync(source) || existsSync(target)) continue;
    cpSync(source, target, { recursive: true, force: false });
  }
}

function quoteYamlString(value: string): string {
  return JSON.stringify(value);
}

function pathRelativeToConfigDir(path: string): string {
  return `./${relativePathFromRootToAppData(path)}`;
}

function relativePathFromRootToAppData(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const marker = "/vaults/";
  const index = normalized.lastIndexOf(marker);
  return index >= 0 ? normalized.slice(index + 1) : normalized;
}

function resolveServiceCommand(isPackaged: boolean): string {
  const explicit = process.env.KNOARBOR_DESKTOP_SERVICE_COMMAND?.trim();
  if (explicit) return explicit;
  if (!isPackaged) return "uv";
  const executable = process.platform === "win32" ? "knoar-service.exe" : "knoar-service";
  return join(process.resourcesPath, "service", executable);
}

function readServiceArgs(isPackaged: boolean): string[] {
  const raw = process.env.KNOARBOR_DESKTOP_SERVICE_ARGS?.trim();
  if (raw) {
    return raw.split(/\s+/).filter(Boolean);
  }
  return isPackaged ? [] : ["run", "knoar"];
}

function readPort(value: string | undefined): number {
  if (!value) return 0;
  const port = Number(value);
  return Number.isInteger(port) && port >= 0 && port <= 65535 ? port : 0;
}

function resolveConfigPath(value: string | undefined, appDataRoot: string): string {
  if (value) {
    return isAbsolute(value) ? value : resolve(process.cwd(), value);
  }
  return join(appDataRoot, "config.yaml");
}

function findDesktopRoot(): string {
  let current = dirname(fileURLToPath(import.meta.url));
  while (true) {
    if (existsSync(join(current, "package.json"))) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return process.cwd();
    }
    current = parent;
  }
}

function findRepoRootFromDesktopRoot(): string {
  let current = findDesktopRoot();
  while (true) {
    if (existsSync(join(current, "pyproject.toml"))) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return process.cwd();
    }
    current = parent;
  }
}
